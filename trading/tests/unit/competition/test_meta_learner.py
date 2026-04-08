from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timezone, timedelta
from competition.meta_learner import WalkForwardMetaLearner, EnsembleRouter


class TestWalkForwardMetaLearner:
    def test_should_retrain_initially(self):
        learner = WalkForwardMetaLearner()
        assert learner.should_retrain(datetime.now(timezone.utc)) is True

    def test_should_not_retrain_soon_after(self):
        learner = WalkForwardMetaLearner(retrain_frequency_hours=24)
        learner.model = "sentinel"  # model must be non-None to skip initial retrain
        learner.last_retrain = datetime.now(timezone.utc)
        assert learner.should_retrain(datetime.now(timezone.utc)) is False

    def test_should_retrain_after_interval(self):
        learner = WalkForwardMetaLearner(retrain_frequency_hours=24)
        learner.model = "sentinel"
        learner.last_retrain = datetime.now(timezone.utc) - timedelta(hours=25)
        assert learner.should_retrain(datetime.now(timezone.utc)) is True

    def test_softmax_weights_sum_to_one(self):
        learner = WalkForwardMetaLearner()
        predictions = {"a": 0.5, "b": 0.3, "c": -0.1}
        weights = learner._softmax_weights(predictions)
        assert sum(weights.values()) == pytest.approx(1.0, abs=0.001)

    def test_softmax_higher_prediction_gets_more_weight(self):
        learner = WalkForwardMetaLearner()
        predictions = {"a": 0.5, "b": 0.1, "c": -0.2}
        weights = learner._softmax_weights(predictions)
        assert weights["a"] > weights["b"] > weights["c"]

    def test_fit_and_predict(self):
        learner = WalkForwardMetaLearner()
        # Synthetic training data
        np.random.seed(42)
        n = 100
        X = pd.DataFrame({
            "elo": np.random.randint(800, 1400, n),
            "confidence": np.random.uniform(0.3, 1.0, n),
            "streak": np.random.randint(-5, 10, n),
        })
        y = pd.Series(np.random.randn(n) * 0.01)  # Returns

        learner.fit(X, y)
        assert learner.model is not None

        # Predict weights
        sample = pd.DataFrame({"elo": [1200], "confidence": [0.8], "streak": [3]})
        pred = learner.predict(sample)
        assert len(pred) == 1


class TestEnsembleRouter:
    def test_starts_in_baseline_mode(self):
        router = EnsembleRouter(meta_learner=None, promote_days=7, demote_days=3)
        assert router.active_mode == "baseline"

    def test_promote_after_consecutive_wins(self):
        router = EnsembleRouter(meta_learner=None, promote_days=3, demote_days=2)
        for _ in range(3):
            router.record_daily_comparison(meta_won=True)
        assert router.active_mode == "meta"

    def test_demote_faster_than_promote(self):
        router = EnsembleRouter(meta_learner=None, promote_days=3, demote_days=2)
        # Promote first
        for _ in range(3):
            router.record_daily_comparison(meta_won=True)
        assert router.active_mode == "meta"
        # Demote
        for _ in range(2):
            router.record_daily_comparison(meta_won=False)
        assert router.active_mode == "baseline"

    def test_streak_resets_on_loss(self):
        router = EnsembleRouter(meta_learner=None, promote_days=3, demote_days=2)
        router.record_daily_comparison(meta_won=True)
        router.record_daily_comparison(meta_won=True)
        router.record_daily_comparison(meta_won=False)  # Resets
        router.record_daily_comparison(meta_won=True)
        assert router.active_mode == "baseline"  # Not promoted -- streak broken
