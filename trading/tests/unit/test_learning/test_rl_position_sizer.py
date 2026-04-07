"""Tests for RL-based position sizer (SAC)."""

import numpy as np
import pytest

from learning.rl_position_sizer import (
    RLPositionSizer,
    SizingState,
    TradingSizingEnv,
)


def _make_state(**overrides) -> SizingState:
    """Helper to build a SizingState with sensible defaults."""
    defaults = dict(
        regime="trending_bull",
        signal_strength=0.6,
        signal_confidence=0.8,
        current_volatility=0.2,
        portfolio_heat=0.3,
        recent_pnl=0.01,
        drawdown=-0.05,
    )
    defaults.update(overrides)
    return SizingState(**defaults)


# ── SizingState ────────────────────────────────────────────────────────


class TestSizingState:
    def test_sizing_state_creation(self):
        state = _make_state()
        assert state.regime == "trending_bull"
        assert state.signal_strength == 0.6
        assert state.signal_confidence == 0.8
        assert state.current_volatility == 0.2
        assert state.portfolio_heat == 0.3
        assert state.recent_pnl == 0.01
        assert state.drawdown == -0.05


# ── TradingSizingEnv ───────────────────────────────────────────────────


class TestTradingSizingEnv:
    def test_trading_env_observation_space(self):
        env = TradingSizingEnv(episode_length=10)
        assert env.observation_space.shape == (7,)
        # low bounds
        np.testing.assert_array_equal(
            env.observation_space.low,
            np.array([-1, -1, 0, 0, 0, -1, -1], dtype=np.float32),
        )
        # high bounds
        np.testing.assert_array_equal(
            env.observation_space.high,
            np.array([1, 1, 1, 5, 1, 1, 0], dtype=np.float32),
        )

    def test_trading_env_action_space(self):
        env = TradingSizingEnv()
        assert env.action_space.shape == (1,)
        assert float(env.action_space.low[0]) == 0.0
        assert float(env.action_space.high[0]) == 1.0

    def test_trading_env_reset(self):
        env = TradingSizingEnv(episode_length=5)
        history = [{"state": _make_state(), "signal_return": 0.01} for _ in range(5)]
        env.set_history(history)
        obs, info = env.reset()
        assert obs.shape == (7,)
        assert isinstance(info, dict)

    def test_trading_env_step(self):
        env = TradingSizingEnv(episode_length=5)
        history = [{"state": _make_state(), "signal_return": 0.02} for _ in range(5)]
        env.set_history(history)
        env.reset()

        action = np.array([0.5], dtype=np.float32)
        obs, reward, terminated, truncated, info = env.step(action)

        assert obs.shape == (7,)
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert truncated is False
        assert isinstance(info, dict)

    def test_trading_env_terminates_at_episode_length(self):
        length = 3
        env = TradingSizingEnv(episode_length=length)
        history = [
            {"state": _make_state(), "signal_return": 0.01} for _ in range(length)
        ]
        env.set_history(history)
        env.reset()

        for i in range(length):
            action = np.array([0.5], dtype=np.float32)
            obs, reward, terminated, truncated, info = env.step(action)

        assert terminated is True


# ── RLPositionSizer ────────────────────────────────────────────────────


class TestRLPositionSizer:
    def test_not_ready_before_min_experience(self):
        sizer = RLPositionSizer(min_experience=10)
        assert not sizer.is_ready
        # Untrained model returns 0.5 default
        result = sizer.predict(_make_state())
        assert result == 0.5

    def test_add_experience_increments_count(self):
        sizer = RLPositionSizer(min_experience=10)
        assert sizer.get_stats()["experience_count"] == 0
        sizer.add_experience(_make_state(), 0.01)
        assert sizer.get_stats()["experience_count"] == 1
        sizer.add_experience(_make_state(regime="trending_bear"), -0.02)
        assert sizer.get_stats()["experience_count"] == 2

    def test_is_ready_after_min_experience(self):
        sizer = RLPositionSizer(min_experience=10)
        for i in range(10):
            sizer.add_experience(
                _make_state(signal_strength=i / 10.0),
                0.01 * (i - 5),
            )
        assert sizer.is_ready

    def test_train_insufficient_data_returns_status(self):
        sizer = RLPositionSizer(min_experience=10)
        sizer.add_experience(_make_state(), 0.01)
        result = sizer.train()
        assert result["status"] == "insufficient_data"
        assert result["experience"] == 1

    @pytest.mark.timeout(30)
    def test_train_returns_metrics(self):
        """Train with small params to keep test fast."""
        sizer = RLPositionSizer(
            min_experience=10,
            train_steps=100,
            episode_length=10,
        )
        for i in range(15):
            sizer.add_experience(
                _make_state(
                    signal_strength=(i - 7) / 7.0,
                    regime="trending_bull" if i % 2 == 0 else "volatile_range",
                ),
                0.02 * (i - 7) / 7.0,
            )
        result = sizer.train()
        assert result["status"] == "trained"
        assert result["experience"] == 15
        assert result["steps"] >= 100  # May be higher due to VecEnv sampling

    @pytest.mark.timeout(30)
    def test_predict_returns_value_in_range(self):
        """After training, predict returns a value in [0, 1]."""
        sizer = RLPositionSizer(
            min_experience=10,
            train_steps=100,
            episode_length=10,
        )
        for i in range(15):
            sizer.add_experience(
                _make_state(signal_strength=(i - 7) / 7.0),
                0.02 * (i - 7) / 7.0,
            )
        sizer.train()

        prediction = sizer.predict(_make_state())
        assert 0.0 <= prediction <= 1.0

    def test_get_stats(self):
        sizer = RLPositionSizer(min_experience=10)
        stats = sizer.get_stats()
        assert stats["experience_count"] == 0
        assert stats["is_trained"] is False
        assert stats["is_ready"] is False
        assert stats["min_experience"] == 10
