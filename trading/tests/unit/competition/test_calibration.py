# tests/unit/competition/test_calibration.py
from __future__ import annotations

import pytest
from competition.calibration import CalibrationTracker


class TestCalibrationTracker:
    def test_initial_score_is_neutral(self):
        tracker = CalibrationTracker(window_size=10)
        score = tracker.get_calibration("agent_a", "high")
        assert score == 1.0  # No data = fully calibrated

    def test_perfect_calibration(self):
        tracker = CalibrationTracker(window_size=5)
        for _ in range(5):
            tracker.record("agent_a", "high", correct=True)
        assert tracker.get_calibration("agent_a", "high") == 1.0

    def test_poor_calibration(self):
        tracker = CalibrationTracker(window_size=5)
        for _ in range(5):
            tracker.record("agent_a", "high", correct=False)
        assert tracker.get_calibration("agent_a", "high") == 0.0

    def test_rolling_window(self):
        tracker = CalibrationTracker(window_size=3)
        tracker.record("agent_a", "high", correct=True)
        tracker.record("agent_a", "high", correct=True)
        tracker.record("agent_a", "high", correct=False)
        # 2/3 correct
        assert tracker.get_calibration("agent_a", "high") == pytest.approx(
            2 / 3, abs=0.01
        )
        # Add another correct — window slides
        tracker.record("agent_a", "high", correct=True)
        # Now: [True, False, True] = 2/3
        assert tracker.get_calibration("agent_a", "high") == pytest.approx(
            2 / 3, abs=0.01
        )

    def test_should_clamp_below_threshold(self):
        tracker = CalibrationTracker(window_size=10, clamp_threshold=0.65)
        for _ in range(10):
            tracker.record("agent_a", "high", correct=False)
        assert tracker.should_clamp("agent_a", "high") is True

    def test_no_clamp_above_threshold(self):
        tracker = CalibrationTracker(window_size=10, clamp_threshold=0.65)
        for _ in range(10):
            tracker.record("agent_a", "high", correct=True)
        assert tracker.should_clamp("agent_a", "high") is False

    def test_effective_confidence_band(self):
        tracker = CalibrationTracker(window_size=5, clamp_threshold=0.65)
        for _ in range(5):
            tracker.record("agent_a", "high", correct=False)
        # Should clamp "high" down to "medium"
        assert tracker.effective_band("agent_a", "high") == "medium"
        # Medium stays medium (not yet clamped further since no medium records)
        assert tracker.effective_band("agent_a", "medium") == "medium"
