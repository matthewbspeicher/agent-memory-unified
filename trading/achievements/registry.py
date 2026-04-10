"""
Achievement System - Badge Registry

Defines all achievements and their unlock criteria.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class AchievementCategory(Enum):
    """Category grouping for achievements."""

    TRADING = "trading"
    CONSISTENCY = "consistency"
    PERFORMANCE = "performance"
    RESILIENCE = "resilience"
    SPECIAL = "special"


@dataclass
class AchievementDefinition:
    """Definition of a single achievement."""

    id: str
    name: str
    description: str
    icon: str
    category: AchievementCategory
    criteria_fn: Callable[[dict], bool]
    xp_reward: int = 100
    rarity: str = "common"  # common, rare, epic, legendary


# Registry of all achievements
ACHIEVEMENTS: dict[str, AchievementDefinition] = {}


def _register_achievement(achievement: AchievementDefinition):
    """Register an achievement in the global registry."""
    ACHIEVEMENTS[achievement.id] = achievement


# ============================================================
# Achievement Definitions
# ============================================================

# --- Trading Milestones ---

_register_achievement(
    AchievementDefinition(
        id="first_trade",
        name="First Blood",
        description="Complete your first trade",
        icon="🎯",
        category=AchievementCategory.TRADING,
        criteria_fn=lambda ctx: ctx.get("total_trades", 0) >= 1,
        xp_reward=50,
        rarity="common",
    )
)

_register_achievement(
    AchievementDefinition(
        id="ten_bagger",
        name="Ten Trades",
        description="Execute 10 trades",
        icon="📈",
        category=AchievementCategory.TRADING,
        criteria_fn=lambda ctx: ctx.get("total_trades", 0) >= 10,
        xp_reward=100,
        rarity="common",
    )
)

_register_achievement(
    AchievementDefinition(
        id="fifty_club",
        name="Fifty Club",
        description="Execute 50 trades",
        icon="🏆",
        category=AchievementCategory.TRADING,
        criteria_fn=lambda ctx: ctx.get("total_trades", 0) >= 50,
        xp_reward=250,
        rarity="rare",
    )
)

_register_achievement(
    AchievementDefinition(
        id="hundred_hero",
        name="Hundred Hero",
        description="Execute 100 trades",
        icon="💯",
        category=AchievementCategory.TRADING,
        criteria_fn=lambda ctx: ctx.get("total_trades", 0) >= 100,
        xp_reward=500,
        rarity="epic",
    )
)


# --- Consistency ---

_register_achievement(
    AchievementDefinition(
        id="streak_3",
        name="Hot Streak",
        description="Be profitable 3 days in a row",
        icon="🔥",
        category=AchievementCategory.CONSISTENCY,
        criteria_fn=lambda ctx: ctx.get("consecutive_profitable_days", 0) >= 3,
        xp_reward=75,
        rarity="common",
    )
)

_register_achievement(
    AchievementDefinition(
        id="streak_5",
        name="On Fire",
        description="Be profitable 5 days in a row",
        icon="🔥🔥",
        category=AchievementCategory.CONSISTENCY,
        criteria_fn=lambda ctx: ctx.get("consecutive_profitable_days", 0) >= 5,
        xp_reward=150,
        rarity="rare",
    )
)

_register_achievement(
    AchievementDefinition(
        id="streak_10",
        name="Unstoppable",
        description="Be profitable 10 days in a row",
        icon="🌶️",
        category=AchievementCategory.CONSISTENCY,
        criteria_fn=lambda ctx: ctx.get("consecutive_profitable_days", 0) >= 10,
        xp_reward=400,
        rarity="epic",
    )
)


# --- Performance ---

_register_achievement(
    AchievementDefinition(
        id="sharpe_king",
        name="Sharpe Master",
        description="Achieve the best Sharpe ratio this month",
        icon="📊",
        category=AchievementCategory.PERFORMANCE,
        criteria_fn=lambda ctx: ctx.get("is_best_sharpe_this_month", False),
        xp_reward=300,
        rarity="epic",
    )
)

_register_achievement(
    AchievementDefinition(
        id="win_rate_70",
        name="Win Machine",
        description="Achieve 70% win rate",
        icon="🎯",
        category=AchievementCategory.PERFORMANCE,
        criteria_fn=lambda ctx: (ctx.get("win_rate", 0) or 0) >= 0.70,
        xp_reward=200,
        rarity="rare",
    )
)

_register_achievement(
    AchievementDefinition(
        id="triple_digit_return",
        name="Triple Digit",
        description="Return over 100% in a single month",
        icon="💰",
        category=AchievementCategory.PERFORMANCE,
        criteria_fn=lambda ctx: ctx.get("monthly_return_pct", 0) >= 100,
        xp_reward=500,
        rarity="legendary",
    )
)


# --- Resilience ---

_register_achievement(
    AchievementDefinition(
        id="comeback_kid",
        name="Comeback Kid",
        description="Recover from a 10%+ drawdown to profit",
        icon="💪",
        category=AchievementCategory.RESILIENCE,
        criteria_fn=lambda ctx: ctx.get("recovered_from_drawdown", False),
        xp_reward=250,
        rarity="rare",
    )
)

_register_achievement(
    AchievementDefinition(
        id="survivor",
        name="Survivor",
        description="Survive a 20%+ drawdown without giving up",
        icon="🛡️",
        category=AchievementCategory.RESILIENCE,
        criteria_fn=lambda ctx: ctx.get("survived_major_drawdown", False),
        xp_reward=300,
        rarity="epic",
    )
)


# --- Special ---

_register_achievement(
    AchievementDefinition(
        id="diamond_hands",
        name="Diamond Hands",
        description="Hold a position 24h+ with 5%+ profit",
        icon="💎",
        category=AchievementCategory.SPECIAL,
        criteria_fn=lambda ctx: ctx.get("held_position_24h_5pct", False),
        xp_reward=200,
        rarity="rare",
    )
)

_register_achievement(
    AchievementDefinition(
        id="paper_champion",
        name="Paper Champion",
        description="Achieve highest paper trading balance",
        icon="📄",
        category=AchievementCategory.SPECIAL,
        criteria_fn=lambda ctx: ctx.get("is_paper_leader", False),
        xp_reward=350,
        rarity="epic",
    )
)

_register_achievement(
    AchievementDefinition(
        id="early_adopter",
        name="Early Adopter",
        description="Be among the first to use the trading system",
        icon="🌅",
        category=AchievementCategory.SPECIAL,
        criteria_fn=lambda ctx: ctx.get("is_early_adopter", False),
        xp_reward=100,
        rarity="rare",
    )
)


def get_achievement(id: str) -> AchievementDefinition | None:
    """Get an achievement by ID."""
    return ACHIEVEMENTS.get(id)


def get_all_achievements() -> dict[str, AchievementDefinition]:
    """Get all registered achievements."""
    return ACHIEVEMENTS.copy()


def get_achievements_by_category(
    category: AchievementCategory,
) -> list[AchievementDefinition]:
    """Get all achievements in a category."""
    return [a for a in ACHIEVEMENTS.values() if a.category == category]
