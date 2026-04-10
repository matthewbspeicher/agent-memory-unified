"""Tests for MetaLearner — XGBoost meta-learner for signal combination."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from learning.meta_learner import MetaLearner, SignalSnapshot


def _make_snapshot(
    agent_a_signal: float,
    agent_b_signal: float,
    agent_a_conf: float = 0.8,
    agent_b_conf: float = 0.8,
    realized_return: float | None = None,
    ts_offset_minutes: int = 0,
) -> SignalSnapshot:
    """Helper to build a SignalSnapshot."""
    return SignalSnapshot(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc)
        + timedelta(minutes=ts_offset_minutes),
        agent_signals={"agent_a": agent_a_signal, "agent_b": agent_b_signal},
        agent_confidences={"agent_a": agent_a_conf, "agent_b": agent_b_conf},
        realized_return=realized_return,
    )


def _generate_nonlinear_dataset(
    n: int,
    seed: int = 42,
) -> list[SignalSnapshot]:
    """Generate snapshots where return is positive iff agent_a > 0.5 AND agent_b > 0.3.

    This non-linear interaction cannot be captured by simple linear weighting.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    snapshots: list[SignalSnapshot] = []
    for i in range(n):
        a_sig = rng.uniform(-1, 1)
        b_sig = rng.uniform(-1, 1)
        a_conf = rng.uniform(0.5, 1.0)
        b_conf = rng.uniform(0.5, 1.0)

        # Non-linear rule: positive return only when BOTH conditions met
        if a_sig > 0.5 and b_sig > 0.3:
            ret = abs(rng.normal(0.02, 0.005))  # positive return
        else:
            ret = -abs(rng.normal(0.02, 0.005))  # negative return

        snapshots.append(
            SignalSnapshot(
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc)
                + timedelta(minutes=i),
                agent_signals={"agent_a": a_sig, "agent_b": b_sig},
                agent_confidences={"agent_a": a_conf, "agent_b": b_conf},
                realized_return=ret,
            )
        )
    return snapshots


class TestMetaLearnerNotReady:
    """Test behaviour before model has sufficient data."""

    def test_not_ready_before_min_samples(self):
        ml = MetaLearner(
            feature_names=["agent_a", "agent_b"],
            min_samples=100,
        )
        # Add fewer than min_samples
        for i in range(50):
            ml.add_snapshot(
                _make_snapshot(0.5, 0.3, realized_return=0.01, ts_offset_minutes=i)
            )

        assert ml.is_ready is False
        direction, confidence = ml.predict(
            signals={"agent_a": 0.6, "agent_b": 0.4},
            confidences={"agent_a": 0.8, "agent_b": 0.8},
        )
        assert direction == 0.0
        assert confidence == 0.0


class TestMetaLearnerFitPredict:
    """Test training and prediction with sufficient data."""

    def test_fit_and_predict_basic(self):
        """Model should learn the non-linear interaction pattern."""
        ml = MetaLearner(
            feature_names=["agent_a", "agent_b"],
            min_samples=100,
            calibration_window=500,
            retrain_interval=50,
        )
        snapshots = _generate_nonlinear_dataset(300)
        for snap in snapshots:
            ml.add_snapshot(snap)

        assert ml.is_ready is True

        # Case 1: Both conditions met -> should predict positive direction
        direction, confidence = ml.predict(
            signals={"agent_a": 0.8, "agent_b": 0.6},
            confidences={"agent_a": 0.9, "agent_b": 0.9},
        )
        assert direction > 0, f"Expected positive direction, got {direction}"
        assert confidence > 0, f"Expected positive confidence, got {confidence}"

        # Case 2: Only agent_a high -> should predict negative direction
        direction2, confidence2 = ml.predict(
            signals={"agent_a": 0.8, "agent_b": -0.5},
            confidences={"agent_a": 0.9, "agent_b": 0.9},
        )
        assert direction2 < 0, f"Expected negative direction, got {direction2}"

        # Case 3: Both low -> should predict negative direction
        direction3, confidence3 = ml.predict(
            signals={"agent_a": -0.5, "agent_b": -0.5},
            confidences={"agent_a": 0.9, "agent_b": 0.9},
        )
        assert direction3 < 0, f"Expected negative direction, got {direction3}"


class TestMetaLearnerWalkForward:
    """Test walk-forward retraining."""

    def test_walk_forward_retrains(self):
        """Model should retrain when retrain_interval new observations arrive."""
        ml = MetaLearner(
            feature_names=["agent_a", "agent_b"],
            min_samples=50,
            calibration_window=200,
            retrain_interval=20,
        )
        snapshots = _generate_nonlinear_dataset(200)
        for snap in snapshots:
            ml.add_snapshot(snap)

        assert ml.is_ready is True
        # Record the number of times model was trained
        initial_train_count = ml._train_count

        # Add retrain_interval more observations to trigger retrain
        extra = _generate_nonlinear_dataset(25, seed=99)
        for snap in extra:
            ml.add_snapshot(snap)

        assert ml._train_count > initial_train_count, (
            "Model should have retrained after adding retrain_interval observations"
        )


class TestMetaLearnerFeatureImportance:
    """Test feature importance reporting."""

    def test_feature_importance_returns_all_agents(self):
        ml = MetaLearner(
            feature_names=["agent_a", "agent_b"],
            min_samples=100,
        )
        snapshots = _generate_nonlinear_dataset(150)
        for snap in snapshots:
            ml.add_snapshot(snap)

        importance = ml.get_feature_importance()

        # Should have entries for each agent (signal + confidence features)
        assert "agent_a_signal" in importance
        assert "agent_b_signal" in importance
        assert "agent_a_confidence" in importance
        assert "agent_b_confidence" in importance

        # All importance values should be non-negative
        for val in importance.values():
            assert val >= 0.0


class TestMetaLearnerEdgeCases:
    """Test edge cases and graceful degradation."""

    def test_add_snapshot_without_realized_return(self):
        """Snapshots without realized_return should be stored but not used for training."""
        ml = MetaLearner(
            feature_names=["agent_a", "agent_b"],
            min_samples=100,
        )
        # Add snapshots without outcomes
        for i in range(120):
            ml.add_snapshot(
                _make_snapshot(0.5, 0.3, realized_return=None, ts_offset_minutes=i)
            )

        # Model should NOT be ready (no labeled data)
        assert ml.is_ready is False

    def test_calibration_window_limits_training_data(self):
        """Old data beyond the calibration window should not be used for training."""
        window_size = 100
        ml = MetaLearner(
            feature_names=["agent_a", "agent_b"],
            min_samples=50,
            calibration_window=window_size,
            retrain_interval=10,
        )

        snapshots = _generate_nonlinear_dataset(200)
        for snap in snapshots:
            ml.add_snapshot(snap)

        # The training data should be limited to the window
        labeled = [s for s in ml._snapshots if s.realized_return is not None]
        # We only care that the model uses the window; check internal state
        # after fit, the effective training size should be <= window_size
        assert ml._last_train_size <= window_size

    def test_predict_with_unknown_agent(self):
        """Prediction with an agent not seen in training should handle gracefully."""
        ml = MetaLearner(
            feature_names=["agent_a", "agent_b"],
            min_samples=50,
        )
        snapshots = _generate_nonlinear_dataset(100)
        for snap in snapshots:
            ml.add_snapshot(snap)

        assert ml.is_ready is True

        # Predict with an extra agent not in training
        direction, confidence = ml.predict(
            signals={"agent_a": 0.8, "agent_b": 0.6, "agent_c": 0.9},
            confidences={"agent_a": 0.9, "agent_b": 0.9, "agent_c": 0.7},
        )
        # Should still return valid results, ignoring unknown agent
        assert isinstance(direction, float)
        assert isinstance(confidence, float)
        assert -1.0 <= direction <= 1.0
        assert 0.0 <= confidence <= 1.0

    def test_predict_with_missing_agent(self):
        """Prediction missing a known agent should fill with 0.0."""
        ml = MetaLearner(
            feature_names=["agent_a", "agent_b"],
            min_samples=50,
        )
        snapshots = _generate_nonlinear_dataset(100)
        for snap in snapshots:
            ml.add_snapshot(snap)

        assert ml.is_ready is True

        # Predict with only one of the two agents
        direction, confidence = ml.predict(
            signals={"agent_a": 0.8},
            confidences={"agent_a": 0.9},
        )
        assert isinstance(direction, float)
        assert isinstance(confidence, float)
