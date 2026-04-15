"""Tests for Brier / ECE calibration metrics."""

from __future__ import annotations

import pytest

from eval.probability_metrics import (
    brier_score,
    calibration_report,
    expected_calibration_error,
)


# --- Brier score -------------------------------------------------------------


def test_brier_perfect_forecaster_is_zero():
    # Every prediction matches outcome exactly
    assert brier_score([0.0, 1.0, 0.0, 1.0], [0, 1, 0, 1]) == 0.0


def test_brier_always_fifty_percent_on_balanced_data():
    # 4 predictions of 0.5 against 2 YES, 2 NO outcomes
    # Each (0.5 - y)^2 = 0.25 regardless of y
    assert brier_score([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]) == pytest.approx(0.25)


def test_brier_worst_case_is_one():
    # Always predict wrong with 100% confidence
    assert brier_score([0.0, 1.0], [1, 0]) == 1.0


def test_brier_validates_input_lengths():
    with pytest.raises(ValueError):
        brier_score([0.5], [1, 0])


def test_brier_rejects_empty():
    with pytest.raises(ValueError):
        brier_score([], [])


# --- ECE ---------------------------------------------------------------------


def test_ece_perfect_calibration_is_zero():
    # Within each bucket, mean prediction == mean outcome
    preds = [0.25, 0.25, 0.25, 0.25, 0.75, 0.75, 0.75, 0.75]
    outs = [0, 1, 0, 0, 1, 1, 0, 1]  # bucket[2]: 1/4 YES, bucket[7]: 3/4 YES
    # Bucket for 0.25: mean_p=0.25, mean_y=0.25 → gap 0
    # Bucket for 0.75: mean_p=0.75, mean_y=0.75 → gap 0
    assert expected_calibration_error(preds, outs, n_buckets=10) == pytest.approx(0.0)


def test_ece_systematic_overconfidence():
    # Always predict 0.9 but only 50% resolve YES → big gap in one bucket
    preds = [0.9] * 10
    outs = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
    # One bucket (idx 9): mean_p=0.9, mean_y=0.5, weight 10/10=1.0, gap=0.4
    assert expected_calibration_error(preds, outs, n_buckets=10) == pytest.approx(0.4)


def test_ece_places_prob_one_in_last_bucket():
    # Probability exactly 1.0 should not overflow into a nonexistent bucket
    preds = [1.0, 1.0]
    outs = [1, 1]
    # Last bucket (idx 9) mean_p=1.0, mean_y=1.0, gap=0
    assert expected_calibration_error(preds, outs, n_buckets=10) == 0.0


def test_ece_ignores_empty_buckets():
    # All predictions in one bucket; other 9 buckets empty
    preds = [0.5, 0.5]
    outs = [1, 0]
    # Bucket 5: mean_p=0.5, mean_y=0.5, gap=0
    assert expected_calibration_error(preds, outs, n_buckets=10) == 0.0


def test_ece_validates_input():
    with pytest.raises(ValueError):
        expected_calibration_error([0.5], [1, 0])
    with pytest.raises(ValueError):
        expected_calibration_error([], [])
    with pytest.raises(ValueError):
        expected_calibration_error([0.5], [1], n_buckets=0)


# --- report ------------------------------------------------------------------


def test_calibration_report_returns_both_metrics_and_summary():
    preds = [0.3, 0.5, 0.7, 0.9]
    outs = [0, 1, 1, 1]

    r = calibration_report(preds, outs, n_buckets=4)

    assert r.n == 4
    assert r.bucket_count == 4
    assert r.mean_prediction == pytest.approx(0.6)
    assert r.resolved_yes_rate == 0.75
    assert r.brier == pytest.approx(brier_score(preds, outs))
    assert r.ece == pytest.approx(
        expected_calibration_error(preds, outs, n_buckets=4)
    )
