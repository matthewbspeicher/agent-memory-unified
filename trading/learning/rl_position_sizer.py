"""SAC reinforcement learning for dynamic position sizing.

Uses Soft Actor-Critic to learn optimal position sizing based on:
- Current market regime (trending_bull, trending_bear, volatile_range, quiet)
- Signal features (strength, confidence)
- Portfolio state (volatility, heat, recent PnL, drawdown)

The agent learns to maximize risk-adjusted returns (Sharpe ratio).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import gymnasium as gymnasium
import numpy as np

logger = logging.getLogger(__name__)

# Regime encoding (for index lookup only)
REGIME_MAP = {
    "trending_bull": 0,
    "trending_bear": 1,
    "volatile_range": 2,
    "quiet": 3,
}

# Regime to numeric (for compact encoding as 2 features)
REGIME_NUMERIC = {
    "trending_bull": (1.0, 0.5),  # trending up
    "trending_bear": (-1.0, 0.5),  # trending down
    "volatile_range": (0.0, 1.0),  # high volatility
    "quiet": (0.0, 0.0),  # calm
}


@dataclass
class SizingState:
    """State representation for position sizing decisions.

    Attributes:
        regime: Current market regime
        signal_strength: Signal strength from 0 to 1
        signal_confidence: Confidence in the signal from 0 to 1
        current_volatility: Recent volatility (annualized)
        portfolio_heat: Current portfolio risk exposure 0-1
        recent_pnl: Recent PnL (last N trades)
        drawdown: Current drawdown (negative = loss)
    """

    regime: str = "quiet"
    signal_strength: float = 0.5
    signal_confidence: float = 0.5
    current_volatility: float = 0.2
    portfolio_heat: float = 0.3
    recent_pnl: float = 0.0
    drawdown: float = 0.0

    def to_observation(self) -> np.ndarray:
        """Convert state to normalized observation vector (7 dims).

        Maps to: [regime_dir, regime_vol, signal_strength, signal_confidence*5, heat, pnl, drawdown]
        """
        # Regime encoding as 2 continuous features
        # dim 0: regime direction (bull=1, bear=-1, volatile=0, quiet=0)
        # dim 1: regime volatility (volatile=1, others=0)
        regime_dir = {
            "trending_bull": 1.0,
            "trending_bear": -1.0,
            "volatile_range": 0.0,
            "quiet": 0.0,
        }.get(self.regime, 0.0)

        regime_vol = 1.0 if self.regime == "volatile_range" else 0.0

        # Normalize continuous features
        signal_strength = float(np.clip(self.signal_strength, 0.0, 1.0))
        signal_confidence = (
            float(np.clip(self.signal_confidence, 0.0, 1.0)) * 5.0
        )  # scale to 0-5
        heat = float(np.clip(self.portfolio_heat, 0.0, 1.0))
        pnl = float(np.clip(self.recent_pnl / 0.2, -1.0, 1.0))
        drawdown = float(np.clip(self.drawdown / -0.2, -1.0, 0.0))

        return np.array(
            [
                regime_dir,
                regime_vol,
                signal_strength,
                signal_confidence,
                heat,
                pnl,
                drawdown,
            ],
            dtype=np.float32,
        )


class TradingSizingEnv(gymnasium.Env):
    """Gymnasium-compatible environment for position sizing.

    Observation space: 7 dimensions
    - regime_dir: -1 to 1 (bull=1, bear=-1, others=0)
    - regime_vol: 0 or 1 (volatile=1)
    - signal_strength: 0 to 1
    - signal_confidence: 0 to 5
    - heat: 0 to 1
    - pnl: -1 to 1
    - drawdown: -1 to 0

    Action space: Box(0, 1) - position size as fraction of max position

    Reward: Sharpe-like ratio combining returns and risk
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        episode_length: int = 30,
        history: list[dict[str, Any]] | None = None,
    ):
        super().__init__()
        from gymnasium import spaces

        self.episode_length = episode_length
        self.history = history or []
        self.current_step = 0
        self._cumulative_return = 0.0
        self._cumulative_risk = 0.0

        # Define spaces using gymnasium directly
        self.observation_space = spaces.Box(
            low=np.array([-1, -1, 0, 0, 0, -1, -1], dtype=np.float32),
            high=np.array([1, 1, 1, 5, 1, 1, 0], dtype=np.float32),
            dtype=np.float32,
        )
        self.action_space = spaces.Box(
            low=np.array([0.0], dtype=np.float32),
            high=np.array([1.0], dtype=np.float32),
            dtype=np.float32,
        )

    def set_history(self, history: list[dict[str, Any]]) -> None:
        """Set historical trading data for training.

        Args:
            history: List of dicts with keys: state (SizingState), signal_return (float)
        """
        self.history = history

    def reset(self, seed: int | None = None, options: dict | None = None):
        """Reset environment to start of episode."""
        self.current_step = 0
        self._cumulative_return = 0.0
        self._cumulative_risk = 0.0

        # Get initial state from history or default
        if self.history and self.current_step < len(self.history):
            state = self.history[self.current_step]["state"]
        else:
            state = SizingState()

        obs = state.to_observation()
        info = {"step": 0, "episode_return": 0.0}
        return obs, info

    def step(self, action: np.ndarray):
        """Execute one step in the environment.

        Args:
            action: Position size [0, 1]

        Returns:
            observation, reward, terminated, truncated, info
        """
        position_size = float(np.clip(action[0], 0.0, 1.0))

        # Get signal return from history
        signal_return = 0.0
        if self.history and self.current_step < len(self.history):
            signal_return = self.history[self.current_step].get("signal_return", 0.0)

        # Calculate reward: position_size * signal_return, penalized by risk
        # Using a Sharpe-like metric: return / (risk + epsilon)
        if self.current_step > 0:
            # Risk is based on position size and volatility
            state = (
                self.history[self.current_step]["state"]
                if self.history and self.current_step < len(self.history)
                else SizingState()
            )
            risk = position_size * state.current_volatility
            risk = max(risk, 0.001)  # prevent division by zero

            # Reward combines return and risk-adjusted performance
            raw_return = position_size * signal_return
            # Sharpe-like: (return - baseline) / risk
            reward = raw_return / risk
        else:
            reward = 0.0

        # Update cumulative metrics
        self._cumulative_return += position_size * signal_return
        self._cumulative_risk += position_size

        self.current_step += 1

        # Determine episode end
        terminated = self.current_step >= self.episode_length
        truncated = (
            self.current_step >= len(self.history) if self.history else terminated
        )

        # Get next observation
        if self.history and self.current_step < len(self.history):
            next_state = self.history[self.current_step]["state"]
        else:
            next_state = SizingState()

        obs = next_state.to_observation()

        info = {
            "step": self.current_step,
            "position_size": position_size,
            "signal_return": signal_return,
            "cumulative_return": self._cumulative_return,
            "cumulative_risk": self._cumulative_risk,
        }

        return obs, reward, terminated, truncated, info

    def render(self):
        """Render not implemented for this env."""
        pass


class RLPositionSizer:
    """SAC-based position sizing agent.

    Learns to size positions based on market state to maximize risk-adjusted returns.
    Falls back to default 0.5 size until trained.
    """

    def __init__(
        self,
        min_experience: int = 50,
        train_steps: int = 1000,
        episode_length: int = 30,
        learning_rate: float = 3e-4,
        buffer_size: int = 10000,
    ):
        self.min_experience = min_experience
        self.train_steps = train_steps
        self.episode_length = episode_length
        self.learning_rate = learning_rate
        self.buffer_size = buffer_size

        self._experience: list[tuple[SizingState, float]] = []
        self._is_trained = False

        # Placeholder model (will be created on first train)
        self._model: Any = None
        self._env: TradingSizingEnv | None = None

        logger.info(
            "RLPositionSizer initialized: min_experience=%d, train_steps=%d",
            min_experience,
            train_steps,
        )

    @property
    def is_ready(self) -> bool:
        """Whether the model has enough experience to train."""
        return len(self._experience) >= self.min_experience

    @property
    def is_trained(self) -> bool:
        """Whether the model has been trained."""
        return self._is_trained

    def add_experience(self, state: SizingState, signal_return: float) -> None:
        """Add a training sample.

        Args:
            state: The market/signal state
            signal_return: The realized return from following this signal
        """
        self._experience.append((state, signal_return))
        logger.debug(
            "Added experience: regime=%s, return=%.4f, total=%d",
            state.regime,
            signal_return,
            len(self._experience),
        )

    def _build_env(self) -> TradingSizingEnv:
        """Build training environment from experience data."""
        env = TradingSizingEnv(episode_length=self.episode_length)

        # Convert experience to history format
        history = [
            {"state": state, "signal_return": signal_return}
            for state, signal_return in self._experience
        ]

        # Repeat history to fill episode length
        if history:
            full_history = history * ((self.episode_length // len(history)) + 1)
            full_history = full_history[: self.episode_length]
            env.set_history(full_history)

        return env

    def train(self) -> dict[str, Any]:
        """Train the SAC model on collected experience.

        Returns:
            Training result with status and metrics
        """
        if len(self._experience) < self.min_experience:
            return {
                "status": "insufficient_data",
                "experience": len(self._experience),
                "required": self.min_experience,
            }

        logger.info("Starting RL training with %d samples", len(self._experience))

        try:
            # Import SB3 components
            from stable_baselines3 import SAC
            from stable_baselines3.common.callbacks import BaseCallback

            # Custom callback for logging
            class TrainingCallback(BaseCallback):
                def __init__(self):
                    super().__init__()
                    self.iteration = 0

                def _on_step(self) -> bool:
                    self.iteration += 1
                    return True

            callback = TrainingCallback()

            # Use stable-baselines3's wrapper for gymnasium environments
            from stable_baselines3.common.vec_env import DummyVecEnv

            # Create env using SB3's monitor wrapper for gymnasium compatibility
            from stable_baselines3.common.monitor import Monitor

            self._env = self._build_env()
            # Wrap in Monitor to make SB3 compatible with gymnasium
            wrapped_env = Monitor(self._env)
            venv = DummyVecEnv([lambda: wrapped_env])

            # Create SAC model with wrapped environment
            # Hyperparameters tuned for financial position sizing
            self._model = SAC(
                "MlpPolicy",
                venv,
                learning_rate=self.learning_rate,
                buffer_size=self.buffer_size,
                learning_starts=min(100, len(self._experience) // 2),
                batch_size=min(64, len(self._experience) // 4),
                tau=0.005,  # soft update coefficient
                gamma=0.99,  # discount factor
                train_freq=1,
                gradient_steps=1,
                target_update_interval=1,
                verbose=0,
                device="auto",
            )

            # Train
            self._model.learn(
                total_timesteps=self.train_steps,
                callback=callback,
                progress_bar=False,
            )

            self._is_trained = True
            logger.info("RL training complete: %d steps", callback.iteration)

            return {
                "status": "trained",
                "experience": len(self._experience),
                "steps": callback.iteration,
            }

        except ImportError as e:
            logger.warning("stable-baselines3 not available: %s", e)
            return {"status": "unavailable", "error": str(e)}
        except Exception as e:
            logger.error("RL training failed: %s", e)
            return {"status": "error", "error": str(e)}

    def predict(self, state: SizingState) -> float:
        """Predict position size for given state.

        Args:
            state: Current market/signal state

        Returns:
            Position size in [0, 1]
        """
        if not self._is_trained or self._model is None:
            return 0.5  # Default fallback

        try:
            # Convert state to observation
            obs = state.to_observation()

            # Get action from model
            action, _ = self._model.predict(obs, deterministic=True)
            return float(np.clip(action[0], 0.0, 1.0))

        except Exception as e:
            logger.warning("Prediction failed, using default: %s", e)
            return 0.5

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics."""
        return {
            "experience_count": len(self._experience),
            "is_trained": self._is_trained,
            "is_ready": self.is_ready,
            "min_experience": self.min_experience,
            "train_steps": self.train_steps if self.is_ready else None,
        }

    def save(self, path: str) -> None:
        """Save trained model."""
        if self._model is not None:
            self._model.save(path)
            logger.info("Model saved to %s", path)
        else:
            logger.warning("No model to save")

    def load(self, path: str) -> None:
        """Load trained model."""
        try:
            from stable_baselines3 import SAC

            self._model = SAC.load(path)
            self._is_trained = True
            logger.info("Model loaded from %s", path)
        except Exception as e:
            logger.error("Failed to load model: %s", e)
