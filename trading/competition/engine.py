# trading/competition/engine.py
"""ELO rating engine — pure functions, no side effects."""
from __future__ import annotations

import math


def expected_score(rating: int, opponent_rating: int) -> float:
    """ELO expected score: probability of winning."""
    return 1.0 / (1.0 + math.pow(10, (opponent_rating - rating) / 400.0))


def calculate_elo_delta(
    rating: int,
    opponent_rating: int,
    outcome: float,
    k: int = 20,
) -> int:
    """Calculate ELO rating change.

    Args:
        rating: Current player's rating.
        opponent_rating: Opponent's rating.
        outcome: 1.0 = win, 0.5 = draw, 0.0 = loss.
        k: K-factor (higher = more volatile).

    Returns:
        Integer ELO delta (positive = gained, negative = lost).
    """
    expected = expected_score(rating, opponent_rating)
    return round(k * (outcome - expected))


def k_factor_for_confidence(confidence: float, base_k: int = 20) -> int:
    """Adjust K-factor based on signal confidence."""
    if confidence >= 0.8:
        return round(base_k * 2.0)  # 40
    if confidence >= 0.5:
        return base_k  # 20
    return round(base_k * 0.5)  # 10


def k_factor_for_new_competitor(matches_count: int, base_k: int = 20) -> int:
    """New competitors get K*2 for first 10 matches."""
    if matches_count < 10:
        return base_k * 2
    return base_k
