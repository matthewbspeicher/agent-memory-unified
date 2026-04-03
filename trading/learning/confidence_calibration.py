"""Confidence calibration logic: bucketing, sample quality, and sizing recommendations."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from storage.confidence_calibration import ConfidenceCalibrationStore


@dataclass
class ConfidenceCalibrationConfig:
    """Configuration for the confidence calibration system."""

    enabled: bool = True
    bucket_width: float = 0.10
    min_trades_for_usable_bucket: int = 25
    min_trades_for_hard_reject: int = 50
    insufficient_sample_multiplier: float = 0.75
    max_positive_multiplier: float = 1.25
    max_composed_kelly_fraction: float = 0.50
    weak_expectancy_threshold: float = 0.005
    moderate_expectancy_threshold: float = 0.015
    strong_expectancy_threshold: float = 0.03
    allow_reject: bool = False


@dataclass
class CalibrationRecommendation:
    """Sizing/filtering recommendation for a given confidence value."""

    bucket: str
    sample_quality: str
    trade_count: int
    expectancy: float | None
    multiplier: float
    would_reject: bool
    reason: str
    calibrated_score: float | None = None


def assign_bucket(confidence: float | None, bucket_width: float = 0.10) -> str:
    """Assign a confidence value to a fixed-width bucket label.

    None → "unknown"
    Values clamped to [0, 1] before bucketing.
    bucket_width=0.10 produces "0.00-0.10", "0.10-0.20", ..., "0.90-1.00".
    """
    if confidence is None:
        return "unknown"

    clamped = max(0.0, min(1.0, confidence))

    # Special-case exactly 1.0 → falls in the top bucket
    if clamped >= 1.0:
        low = 1.0 - bucket_width
        high = 1.0
    else:
        # Use round to avoid floating-point artifacts (e.g., 0.70/0.10 = 6.9999...)
        bucket_index = math.floor(round(clamped / bucket_width, 10))
        low = bucket_index * bucket_width
        high = low + bucket_width

    # Format to 2 decimal places to avoid floating-point display noise
    return f"{low:.2f}-{high:.2f}"


def classify_sample_quality(trade_count: int) -> str:
    """Classify the statistical quality of a bucket based on trade count.

    < 10      → insufficient
    10 - 24   → weak
    25 - 49   → usable
    >= 50     → strong
    """
    if trade_count < 10:
        return "insufficient"
    if trade_count < 25:
        return "weak"
    if trade_count < 50:
        return "usable"
    return "strong"


def compute_multiplier(
    expectancy_per_notional: float | None,
    sample_quality: str,
    cfg: ConfidenceCalibrationConfig,
) -> float:
    """Compute a size multiplier from expectancy and sample quality.

    Rules (from spec):
    - insufficient sample → insufficient_sample_multiplier (default 0.75x)
    - negative expectancy → 0.0x is handled by the *filter* stage; multiplier
      stage clamps to minimum of 0.25x (never 0.0x via multiplier)
    - weak positive (< weak_threshold) → 0.5x
    - moderate positive (weak–moderate) → 0.75x
    - strong positive (moderate–strong) → 1.0x
    - exceptional + strong sample (> strong_threshold) → max_positive_multiplier (1.25x)

    Returns a multiplier clamped to [0.25, max_positive_multiplier].
    """
    if sample_quality == "insufficient":
        return cfg.insufficient_sample_multiplier

    if expectancy_per_notional is None:
        return cfg.insufficient_sample_multiplier

    if expectancy_per_notional <= 0:
        # Rejection is handled by filter stage; multiplier floor is 0.25x
        return 0.25

    if expectancy_per_notional < cfg.weak_expectancy_threshold:
        raw = 0.5
    elif expectancy_per_notional < cfg.moderate_expectancy_threshold:
        raw = 0.75
    elif expectancy_per_notional < cfg.strong_expectancy_threshold:
        raw = 1.0
    else:
        # Exceptional — only full 1.25x if sample is strong
        raw = cfg.max_positive_multiplier if sample_quality == "strong" else 1.0

    return min(max(raw, 0.25), cfg.max_positive_multiplier)


def compute_calibrated_score(
    expectancy_per_notional: float | None,
    sample_quality: str,
) -> float | None:
    """Simple calibrated score = expectancy_per_notional × sample_weight.

    sample_weight:
      insufficient → 0.0
      weak         → 0.25
      usable       → 0.6
      strong       → 1.0
    """
    if expectancy_per_notional is None:
        return None

    weights = {
        "insufficient": 0.0,
        "weak": 0.25,
        "usable": 0.60,
        "strong": 1.0,
    }
    weight = weights.get(sample_quality, 0.0)
    return expectancy_per_notional * weight


def build_recommendation(
    bucket: str,
    trade_count: int,
    expectancy: float | None,
    avg_net_pnl: float | None,
    cfg: ConfidenceCalibrationConfig,
) -> CalibrationRecommendation:
    """Compute a full CalibrationRecommendation from bucket metrics."""
    sample_quality = classify_sample_quality(trade_count)

    # expectancy_per_notional: use expectancy directly as a normalized return metric.
    # The spec uses "expectancy_per_notional" which equals avg_net_return_pct approximately.
    # We receive expectancy as a float (typically avg_net_pnl or a return figure).
    # Here we use `expectancy` (avg_net_return_pct) directly as the per-notional proxy.
    expectancy_per_notional = expectancy  # caller passes avg_net_return_pct

    calibrated_score = compute_calibrated_score(expectancy_per_notional, sample_quality)
    multiplier = compute_multiplier(expectancy_per_notional, sample_quality, cfg)

    # Filter-stage rejection: only when allow_reject=True AND sample is sufficient
    # AND expectancy is negative AND trade_count >= min_trades_for_hard_reject
    would_reject = False
    if (
        cfg.allow_reject
        and expectancy_per_notional is not None
        and expectancy_per_notional <= 0
        and trade_count >= cfg.min_trades_for_hard_reject
    ):
        would_reject = True

    # Build explanation
    if bucket == "unknown":
        reason = "Unknown confidence — no calibration data available; using fallback multiplier."
    elif sample_quality == "insufficient":
        reason = f"Insufficient sample ({trade_count} trades < 10); using conservative fallback multiplier."
    elif sample_quality == "weak":
        reason = f"Weak sample ({trade_count} trades); applying reduced multiplier."
    elif would_reject:
        reason = (
            f"Negative expectancy ({expectancy_per_notional:.4f}) with {sample_quality} sample "
            f"({trade_count} trades >= {cfg.min_trades_for_hard_reject}); trade rejected."
        )
    elif expectancy_per_notional is not None and expectancy_per_notional <= 0:
        reason = (
            f"Negative expectancy ({expectancy_per_notional:.4f}) but sample below hard-reject "
            f"threshold ({trade_count} < {cfg.min_trades_for_hard_reject}); size reduced to 0.25x."
        )
    else:
        exp_str = f"{expectancy_per_notional:.4f}" if expectancy_per_notional is not None else "N/A"
        reason = (
            f"Bucket {bucket}: {sample_quality} sample ({trade_count} trades), "
            f"expectancy={exp_str}; multiplier={multiplier:.2f}x."
        )

    return CalibrationRecommendation(
        bucket=bucket,
        sample_quality=sample_quality,
        trade_count=trade_count,
        expectancy=expectancy_per_notional,
        multiplier=multiplier,
        would_reject=would_reject,
        reason=reason,
        calibrated_score=calibrated_score,
    )


def apply_composed_kelly_cap(
    base_kelly: float,
    multiplier: float,
    max_composed_kelly_fraction: float,
) -> float:
    """Clamp composed Kelly to never exceed max_composed_kelly_fraction.

    Returns the adjusted multiplier so that base_kelly × multiplier <= cap.
    If base_kelly is 0, returns the multiplier unchanged.
    """
    if base_kelly <= 0:
        return multiplier
    composed = base_kelly * multiplier
    if composed <= max_composed_kelly_fraction:
        return multiplier
    return max_composed_kelly_fraction / base_kelly


# ---------------------------------------------------------------------------
# Summary computation from trade_analytics rows
# ---------------------------------------------------------------------------

_WINDOW_DELTAS: dict[str, timedelta | None] = {
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "all": None,
}


def _window_start(window_label: str) -> str | None:
    delta = _WINDOW_DELTAS.get(window_label)
    if delta is None:
        return None
    return (datetime.now(timezone.utc) - delta).isoformat()


def _compute_bucket_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate trade_analytics rows into a bucket summary dict."""
    trade_count = len(rows)
    wins = [r for r in rows if r.get("realized_outcome") == "win"]
    win_rate = len(wins) / trade_count if trade_count > 0 else 0.0

    net_pnls = [float(r["net_pnl"]) for r in rows if r.get("net_pnl") is not None]
    net_returns = [float(r["net_return_pct"]) for r in rows if r.get("net_return_pct") is not None]

    avg_net_pnl = sum(net_pnls) / len(net_pnls) if net_pnls else 0.0
    avg_net_return_pct = sum(net_returns) / len(net_returns) if net_returns else 0.0

    # Expectancy = avg_net_return_pct (return-based, comparable across sizes)
    expectancy = avg_net_return_pct

    # Profit factor: sum of wins / abs(sum of losses)
    win_pnls = [p for p in net_pnls if p > 0]
    loss_pnls = [p for p in net_pnls if p < 0]
    if loss_pnls:
        profit_factor = sum(win_pnls) / abs(sum(loss_pnls))
    elif win_pnls:
        profit_factor = None  # all wins — technically infinite
    else:
        profit_factor = None

    # Max drawdown: largest single loss as fraction of average entry (simplified)
    max_drawdown = min(net_returns) if net_returns else None

    sample_quality = classify_sample_quality(trade_count)
    calibrated_score = compute_calibrated_score(expectancy, sample_quality)

    return {
        "trade_count": trade_count,
        "win_rate": win_rate,
        "avg_net_pnl": str(round(avg_net_pnl, 4)),
        "avg_net_return_pct": avg_net_return_pct,
        "expectancy": str(round(expectancy, 6)),
        "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
        "max_drawdown": str(round(max_drawdown, 6)) if max_drawdown is not None else None,
        "calibrated_score": round(calibrated_score, 6) if calibrated_score is not None else None,
        "sample_quality": sample_quality,
    }


async def recompute_calibration_for_strategy(
    agent_name: str,
    analytics_rows: list[dict[str, Any]],
    store: ConfidenceCalibrationStore,
    cfg: ConfidenceCalibrationConfig,
    *,
    windows: list[str] | None = None,
) -> None:
    """Recompute and persist calibration summaries for one strategy.

    For each window label and each confidence bucket found in `analytics_rows`,
    computes aggregate metrics and upserts into the store.

    Args:
        agent_name: Strategy name.
        analytics_rows: All trade_analytics rows for this strategy (all time).
        store: ConfidenceCalibrationStore to persist to.
        cfg: Config (bucket_width, thresholds, etc.).
        windows: Window labels to compute. Defaults to ["30d", "90d", "all"].
    """
    if windows is None:
        windows = ["30d", "90d", "all"]

    for window_label in windows:
        ws = _window_start(window_label)

        # Filter rows to window
        if ws is not None:
            window_rows = [r for r in analytics_rows if (r.get("exit_time") or "") >= ws]
        else:
            window_rows = list(analytics_rows)

        # Group by confidence bucket
        bucket_groups: dict[str, list[dict[str, Any]]] = {}
        for row in window_rows:
            confidence = row.get("confidence")
            bucket = assign_bucket(confidence, cfg.bucket_width)
            bucket_groups.setdefault(bucket, []).append(row)

        # Upsert a summary row for each bucket
        for bucket, bucket_rows in bucket_groups.items():
            summary = _compute_bucket_summary(bucket_rows)
            await store.upsert(
                agent_name=agent_name,
                confidence_bucket=bucket,
                window_label=window_label,
                **summary,
            )
