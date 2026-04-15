"""Calibration metrics for probability forecasts against resolved outcomes.

Pure-functional metrics module. No I/O, no async. The eval harness
(kalshi_bench.py) imports these after running the LLM over a dataset.

References:
- Brier score: Glenn W. Brier (1950). Squared error between predicted
  probability and binary outcome. Lower is better, range [0, 1].
- Expected Calibration Error (ECE): Guo et al. (2017). Average gap
  between predicted probability and empirical frequency, bucketed.
  Lower is better, range [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationReport:
    """Summary statistics for a set of (predicted_prob, outcome) pairs."""

    n: int
    brier: float
    ece: float
    bucket_count: int
    mean_prediction: float
    resolved_yes_rate: float


def brier_score(predictions: list[float], outcomes: list[int]) -> float:
    """Mean squared error between predicted probability and {0,1} outcome.

    Each prediction is in [0, 1]; each outcome is 0 or 1.
    Range is [0, 1]; perfect forecaster scores 0, always-50% scores 0.25.
    """
    if len(predictions) != len(outcomes):
        raise ValueError(
            f"predictions and outcomes must be same length; got {len(predictions)} vs {len(outcomes)}"
        )
    if not predictions:
        raise ValueError("cannot compute Brier on empty input")
    total = sum((p - y) ** 2 for p, y in zip(predictions, outcomes))
    return total / len(predictions)


def expected_calibration_error(
    predictions: list[float],
    outcomes: list[int],
    *,
    n_buckets: int = 10,
) -> float:
    """Bucket predictions into `n_buckets` equal-width bins over [0, 1],
    compute the per-bucket gap between mean(prediction) and mean(outcome),
    and return the sample-weighted average gap.

    A perfectly calibrated forecaster has ECE = 0. An always-50% forecaster
    on a base-rate-20% event has ECE = 0.30.
    """
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must be same length")
    if not predictions:
        raise ValueError("cannot compute ECE on empty input")
    if n_buckets < 1:
        raise ValueError("n_buckets must be >= 1")

    # Place each prediction into its bucket. Edge case: prediction = 1.0
    # lands in the last bucket, not a ghost bucket n_buckets+1.
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(n_buckets)]
    for p, y in zip(predictions, outcomes):
        idx = min(int(p * n_buckets), n_buckets - 1)
        buckets[idx].append((p, y))

    n = len(predictions)
    total_weighted_gap = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        mean_p = sum(p for p, _ in bucket) / len(bucket)
        mean_y = sum(y for _, y in bucket) / len(bucket)
        total_weighted_gap += (len(bucket) / n) * abs(mean_p - mean_y)
    return total_weighted_gap


def calibration_report(
    predictions: list[float],
    outcomes: list[int],
    *,
    n_buckets: int = 10,
) -> CalibrationReport:
    """Produce both Brier and ECE in one pass with summary stats."""
    n = len(predictions)
    return CalibrationReport(
        n=n,
        brier=brier_score(predictions, outcomes),
        ece=expected_calibration_error(predictions, outcomes, n_buckets=n_buckets),
        bucket_count=n_buckets,
        mean_prediction=sum(predictions) / n,
        resolved_yes_rate=sum(outcomes) / n,
    )
