"""Pure ranking computation — no store, no EventBus, no metagraph SDK objects."""

from __future__ import annotations

from datetime import datetime

from integrations.bittensor.models import (
    MinerRanking,
    MinerRankingInput,
    RankingConfig,
    RankingWeights,
)

# Weight profiles
DIRECTION_HEAVY = RankingWeights(direction=0.60, magnitude=0.25, path=0.15)
RETURN_SENSITIVE = RankingWeights(direction=0.45, magnitude=0.35, path=0.20)


def _compute_streak_bonus(
    direction_accuracy: float,
    windows_evaluated: int,
    max_streak_bonus: float = 0.15,
) -> float:
    """Compute bonus for consistent performers.

    Miners with >70% direction accuracy over 10+ windows get a bonus
    that increases with accuracy, capping at max_streak_bonus.
    """
    if windows_evaluated < 10 or direction_accuracy < 0.70:
        return 0.0
    excess_accuracy = direction_accuracy - 0.70
    scale = min(1.0, excess_accuracy / 0.30)  # 70%→0%, 100%→100%
    return max_streak_bonus * scale


def _compute_erratic_penalty(
    accuracy_std: float | None,
    windows_evaluated: int,
) -> float:
    """Penalty for miners with highly variable accuracy.

    High standard deviation in accuracy indicates erratic predictions.
    Penalty scales with std dev, starting at 10+ windows.
    """
    if windows_evaluated < 10 or accuracy_std is None:
        return 0.0
    # std > 0.30 is considered very erratic, max penalty 10%
    penalty = min(0.10, accuracy_std * 0.25)
    return penalty


def compute_rankings(
    inputs: list[MinerRankingInput],
    weights: RankingWeights,
    config: RankingConfig,
    now: datetime,
) -> list[MinerRanking]:
    """Compute MinerRanking objects from pre-loaded inputs.

    Pure function — all data must be pre-loaded by the caller.
    """
    if not inputs:
        return []

    # Normalize magnitude errors across the miner set (min-max → [0, 1])
    mag_errors = [inp.mean_magnitude_error for inp in inputs]
    norm_mag = _min_max_normalize(mag_errors)

    # Normalize incentive scores across the miner set
    raw_incentives = [inp.raw_incentive_score for inp in inputs]
    norm_incentives = _min_max_normalize(raw_incentives)

    results: list[MinerRanking] = []
    for i, inp in enumerate(inputs):
        internal = _compute_internal_score(
            direction_accuracy=inp.direction_accuracy,
            norm_magnitude_error=norm_mag[i],
            mean_path_correlation=inp.mean_path_correlation,
            weights=weights,
        )

        # Apply streak bonus for consistent performers
        streak_bonus = _compute_streak_bonus(
            direction_accuracy=inp.direction_accuracy,
            windows_evaluated=inp.windows_evaluated,
        )

        # Apply penalty for erratic miners (high variance in accuracy)
        erratic_penalty = _compute_erratic_penalty(
            accuracy_std=inp.accuracy_std if hasattr(inp, "accuracy_std") else None,
            windows_evaluated=inp.windows_evaluated,
        )

        # Combine: internal + streak_bonus - erratic_penalty
        adjusted_internal = max(0.0, internal + streak_bonus - erratic_penalty)

        alpha = _compute_alpha(inp.windows_evaluated, config)
        hybrid = alpha * norm_incentives[i] + (1.0 - alpha) * adjusted_internal

        results.append(
            MinerRanking(
                miner_hotkey=inp.miner_hotkey,
                windows_evaluated=inp.windows_evaluated,
                direction_accuracy=inp.direction_accuracy,
                mean_magnitude_error=inp.mean_magnitude_error,
                mean_path_correlation=inp.mean_path_correlation,
                internal_score=internal,
                latest_incentive_score=inp.raw_incentive_score,
                hybrid_score=hybrid,
                alpha_used=alpha,
                updated_at=now,
            )
        )
    return results


def _min_max_normalize(values: list[float]) -> list[float]:
    """Min-max scale to [0, 1]. Degenerate case (all equal) returns 0.5 for all."""
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def _compute_internal_score(
    direction_accuracy: float,
    norm_magnitude_error: float,
    mean_path_correlation: float | None,
    weights: RankingWeights,
) -> float:
    """Compute weighted internal score from metric components."""
    dir_component = direction_accuracy
    mag_component = 1.0 - max(0.0, min(1.0, norm_magnitude_error))

    if mean_path_correlation is not None:
        path_component = (mean_path_correlation + 1.0) / 2.0
        return (
            weights.direction * dir_component
            + weights.magnitude * mag_component
            + weights.path * path_component
        )

    remaining = weights.direction + weights.magnitude
    if remaining == 0.0:
        return 0.0
    w_dir = weights.direction / remaining
    w_mag = weights.magnitude / remaining
    return w_dir * dir_component + w_mag * mag_component


def _compute_alpha(windows_evaluated: int, config: RankingConfig) -> float:
    """Threshold-gated alpha decay."""
    if windows_evaluated < config.min_windows_for_ranking:
        return 1.0
    excess = windows_evaluated - config.min_windows_for_ranking
    return max(config.alpha_floor, 1.0 - config.alpha_decay_per_window * excess)
