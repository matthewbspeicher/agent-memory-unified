"""XGBoost walk-forward meta-learner with auto-fallback."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

XGB_CONFIG = {
    "max_depth": 4,
    "n_estimators": 100,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
    "verbosity": 0,
}


class WalkForwardMetaLearner:
    """XGBoost meta-learner with walk-forward validation."""

    def __init__(
        self,
        training_window_days: int = 30,
        gap_days: int = 1,
        retrain_frequency_hours: int = 24,
    ):
        self.training_window = timedelta(days=training_window_days)
        self.gap = timedelta(days=gap_days)
        self.retrain_freq = timedelta(hours=retrain_frequency_hours)
        self.model: Any = None
        self.feature_names: list[str] = []
        self.last_retrain: datetime | None = None
        self.feature_importance: dict[str, float] = {}

    def should_retrain(self, current_time: datetime) -> bool:
        if self.model is None or self.last_retrain is None:
            return True
        return (current_time - self.last_retrain) >= self.retrain_freq

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Train XGBoost model."""
        import xgboost as xgb

        self.feature_names = X.columns.tolist()

        # Train/val split (time-ordered, no shuffle)
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

        self.model = xgb.XGBRegressor(**XGB_CONFIG)
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

        # Store feature importance
        importance = self.model.feature_importances_
        self.feature_importance = dict(zip(self.feature_names, importance.tolist()))

        self.last_retrain = datetime.now(timezone.utc)
        logger.info("meta_learner.trained", extra={
            "features": len(self.feature_names),
            "samples": len(X),
            "top_3": sorted(
                self.feature_importance,
                key=self.feature_importance.get,  # type: ignore[arg-type]
                reverse=True,
            )[:3],
        })

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict expected returns."""
        if self.model is None:
            return np.zeros(len(X))
        return self.model.predict(X)

    def predict_weights(self, competitor_features: dict[str, pd.DataFrame]) -> dict[str, float]:
        """Predict optimal weights for each competitor."""
        if self.model is None:
            n = len(competitor_features)
            return {cid: 1.0 / n for cid in competitor_features} if n else {}

        predictions = {}
        for comp_id, features in competitor_features.items():
            pred = self.predict(features)
            predictions[comp_id] = float(pred.mean()) if len(pred) else 0.0

        return self._softmax_weights(predictions)

    def _softmax_weights(self, predictions: dict[str, float]) -> dict[str, float]:
        """Softmax normalization of predictions to weights."""
        if not predictions:
            return {}
        values = np.array(list(predictions.values()))
        temperature = 0.5
        scaled = values / temperature
        exp_values = np.exp(scaled - np.max(scaled))
        weights = exp_values / exp_values.sum()
        return dict(zip(predictions.keys(), weights.tolist()))


class EnsembleRouter:
    """Routes between meta-learner and baseline with auto-fallback."""

    def __init__(
        self,
        meta_learner: WalkForwardMetaLearner | None,
        promote_days: int = 7,
        demote_days: int = 3,
    ):
        self.meta_learner = meta_learner
        self.promote_days = promote_days
        self.demote_days = demote_days
        self.active_mode: Literal["meta", "baseline"] = "baseline"
        self._meta_win_streak = 0
        self._baseline_win_streak = 0

    def record_daily_comparison(self, meta_won: bool) -> None:
        """Record whether meta-learner outperformed baseline today."""
        if meta_won:
            self._meta_win_streak += 1
            self._baseline_win_streak = 0
        else:
            self._baseline_win_streak += 1
            self._meta_win_streak = 0

        # Check promotion
        if self.active_mode == "baseline" and self._meta_win_streak >= self.promote_days:
            self.active_mode = "meta"
            self._meta_win_streak = 0
            logger.info("ensemble.switched mode=meta_learner")

        # Check demotion
        if self.active_mode == "meta" and self._baseline_win_streak >= self.demote_days:
            self.active_mode = "baseline"
            self._baseline_win_streak = 0
            logger.info("ensemble.switched mode=baseline")

    def get_weights(self, competitor_features: dict[str, pd.DataFrame] | None = None) -> dict[str, float] | None:
        """Get ensemble weights from active mode."""
        if self.active_mode == "meta" and self.meta_learner and competitor_features:
            return self.meta_learner.predict_weights(competitor_features)
        return None  # Caller falls back to linear baseline
