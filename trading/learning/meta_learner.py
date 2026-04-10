"""XGBoost meta-learner for optimal signal combination.

Trains on historical (agent_signals, realized_return) pairs using
walk-forward calibration. Captures non-linear interactions between
signals that linear Kelly/Sharpe weighting misses.

Features: signal strength + confidence per agent (2 features each).
Auto-retrains every N new observations on a rolling window.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from xgboost import XGBRegressor

logger = logging.getLogger(__name__)


@dataclass
class SignalSnapshot:
    """One point in time with all agent signals and the realized outcome."""

    timestamp: datetime
    agent_signals: dict[str, float]  # agent_name -> signal strength (-1 to 1)
    agent_confidences: dict[str, float]  # agent_name -> confidence (0 to 1)
    realized_return: float | None = None  # filled after holding period


class MetaLearner:
    """XGBoost meta-learner for optimal signal combination.

    Trains on historical (agent_signals, realized_return) pairs.
    Predicts direction and confidence for new signal combinations.
    Walk-forward: retrain every N observations on a rolling window.
    """

    def __init__(
        self,
        feature_names: list[str] | None = None,
        calibration_window: int = 500,
        retrain_interval: int = 50,
        min_samples: int = 100,
    ) -> None:
        self._feature_names: list[str] = feature_names or []
        self._calibration_window = calibration_window
        self._retrain_interval = retrain_interval
        self._min_samples = min_samples

        self._snapshots: list[SignalSnapshot] = []
        self._model: XGBRegressor | None = None
        self._obs_since_last_train: int = 0
        self._train_count: int = 0
        self._last_train_size: int = 0

        # Build ordered feature column names: agent_signal, agent_confidence for each
        self._feature_columns: list[str] = self._build_feature_columns(
            self._feature_names
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_snapshot(self, snapshot: SignalSnapshot) -> None:
        """Add a new observation. Auto-retrains if interval reached."""
        self._snapshots.append(snapshot)

        # Discover new agents on the fly
        new_agents: list[str] = []
        for name in snapshot.agent_signals:
            if name not in self._feature_names:
                new_agents.append(name)
                self._feature_names.append(name)
        if new_agents:
            self._feature_columns = self._build_feature_columns(self._feature_names)
            # Invalidate the current model since feature set changed
            self._model = None

        if snapshot.realized_return is not None:
            self._obs_since_last_train += 1

        # Auto-retrain when enough new labeled observations accumulate
        labeled_count = self._count_labeled_in_window()
        if (
            labeled_count >= self._min_samples
            and self._obs_since_last_train >= self._retrain_interval
        ):
            self.fit()

    def predict(
        self,
        signals: dict[str, float],
        confidences: dict[str, float],
    ) -> tuple[float, float]:
        """Predict (direction_score, confidence) from current signals.

        Returns (0.0, 0.0) if model not yet trained (insufficient data).
        direction_score: -1 to 1 (bearish to bullish)
        confidence: 0 to 1
        """
        if not self.is_ready or self._model is None:
            return (0.0, 0.0)

        features = self._signals_to_features(signals, confidences)
        X = np.array([features])
        predicted_return: float = float(self._model.predict(X)[0])

        # Map predicted return to direction and confidence
        direction_score = float(np.clip(np.sign(predicted_return) * min(abs(predicted_return) / 0.03, 1.0), -1.0, 1.0))
        confidence = float(np.clip(abs(predicted_return) / 0.03, 0.0, 1.0))

        return (direction_score, confidence)

    def fit(self) -> None:
        """Train/retrain the model on current window."""
        X, y = self._prepare_training_data()
        if len(y) < self._min_samples:
            return

        model = XGBRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="reg:squarederror",
            random_state=42,
            verbosity=0,
        )
        model.fit(X, y)

        self._model = model
        self._obs_since_last_train = 0
        self._train_count += 1
        self._last_train_size = len(y)

        logger.info(
            "MetaLearner trained (iteration=%d, samples=%d, features=%d)",
            self._train_count,
            len(y),
            X.shape[1],
        )

    @property
    def is_ready(self) -> bool:
        """True if enough data to make predictions."""
        if self._model is not None:
            return True
        # Check if we have enough labeled data and could train
        labeled_count = self._count_labeled_in_window()
        if labeled_count >= self._min_samples:
            # Trigger initial training
            self.fit()
            return self._model is not None
        return False

    def get_feature_importance(self) -> dict[str, float]:
        """Returns feature importance scores for each agent signal."""
        if self._model is None:
            if not self.is_ready:
                return {}

        assert self._model is not None
        importance_array = self._model.feature_importances_
        result: dict[str, float] = {}
        for i, col_name in enumerate(self._feature_columns):
            if i < len(importance_array):
                result[col_name] = float(importance_array[i])
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_feature_columns(agent_names: list[str]) -> list[str]:
        """Build ordered feature column names from agent names."""
        columns: list[str] = []
        for name in agent_names:
            columns.append(f"{name}_signal")
            columns.append(f"{name}_confidence")
        return columns

    def _signals_to_features(
        self,
        signals: dict[str, float],
        confidences: dict[str, float],
    ) -> list[float]:
        """Convert signal/confidence dicts to ordered feature vector.

        Unknown agents (not in feature_names) are ignored.
        Missing agents (in feature_names but not in signals) are filled with 0.0.
        """
        features: list[float] = []
        for name in self._feature_names:
            features.append(signals.get(name, 0.0))
            features.append(confidences.get(name, 0.0))
        return features

    def _count_labeled_in_window(self) -> int:
        """Count snapshots with realized_return in the calibration window."""
        window = self._snapshots[-self._calibration_window :]
        return sum(1 for s in window if s.realized_return is not None)

    def _prepare_training_data(self) -> tuple[np.ndarray, np.ndarray]:
        """Build X, y arrays from snapshots in the calibration window."""
        window = self._snapshots[-self._calibration_window :]
        labeled = [s for s in window if s.realized_return is not None]

        if not labeled:
            return np.empty((0, len(self._feature_columns))), np.empty(0)

        X_rows: list[list[float]] = []
        y_vals: list[float] = []

        for snap in labeled:
            row = self._signals_to_features(snap.agent_signals, snap.agent_confidences)
            X_rows.append(row)
            y_vals.append(snap.realized_return)  # type: ignore[arg-type]

        return np.array(X_rows), np.array(y_vals)
