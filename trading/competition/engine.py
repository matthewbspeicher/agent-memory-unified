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


# ── XP Award Logic ──


def calculate_match_xp(
    won: bool,
    match_type: str = "baseline",
    is_pairwise: bool = False,
) -> int:
    """Calculate XP awarded for a match result.

    Returns 0 for losses (XP only awarded for wins).
    """
    if not won:
        return 0
    if is_pairwise or match_type == "pairwise":
        return 25
    return 10


def check_streak_milestone(current_streak: int, previous_streak: int) -> int:
    """Check if a streak milestone was reached.

    Awards +50 XP for every 5-streak milestone crossed.
    Example: crossing streak 5 awards 50, crossing 10 awards another 50.
    """
    from competition.models import XpSource, XP_AMOUNTS

    prev_milestone = (previous_streak // 5) * 5
    curr_milestone = (current_streak // 5) * 5
    milestones_crossed = (curr_milestone - prev_milestone) // 5
    return milestones_crossed * XP_AMOUNTS[XpSource.STREAK_MILESTONE]


def check_tier_promotion(new_tier: str, old_tier: str) -> int:
    """Check if a tier promotion occurred.

    Awards +100 XP for tier upgrades.
    """
    from competition.models import Tier, XpSource, XP_AMOUNTS

    tier_order = {
        Tier.BRONZE: 0,
        Tier.SILVER: 1,
        Tier.GOLD: 2,
        Tier.DIAMOND: 3,
    }
    old_rank = tier_order.get(Tier(old_tier), 0)
    new_rank = tier_order.get(Tier(new_tier), 0)
    if new_rank > old_rank:
        return XP_AMOUNTS[XpSource.TIER_PROMOTION]
    return 0


def calculate_sharpe_xp(sharpe_ratio: float) -> int:
    from competition.models import XpSource, XP_AMOUNTS

    if sharpe_ratio > 2.0:
        return XP_AMOUNTS[XpSource.SHARPE_MASTER]
    return 0


def check_mission_updates(
    won: bool,
    current_streak: int,
    sharpe_ratio: float | None = None,
    new_achievements: int = 0,
) -> list[tuple[str, int]]:
    from competition.models import MissionId

    updates: list[tuple[str, int]] = []

    if won:
        updates.append((MissionId.WARM_UP.value, 1))
        updates.append((MissionId.WEEKLY_GRIND.value, 1))

    if won and current_streak >= 3:
        updates.append((MissionId.STREAK_STARTER.value, 1))

    if won and current_streak >= 5:
        updates.append((MissionId.STREAK_MASTER.value, 1))

    if sharpe_ratio is not None and sharpe_ratio > 1.5:
        updates.append((MissionId.SHARPE_HUNTER.value, 1))

    if new_achievements > 0:
        updates.append((MissionId.ACHIEVEMENT_HUNTER.value, new_achievements))

    return updates
