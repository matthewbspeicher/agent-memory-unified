# trading/competition/models.py
from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CompetitorType(str, Enum):
    AGENT = "agent"
    MINER = "miner"
    PROVIDER = "provider"


class Tier(str, Enum):
    DIAMOND = "diamond"
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


def tier_for_elo(elo: int) -> Tier:
    if elo >= 1400:
        return Tier.DIAMOND
    if elo >= 1200:
        return Tier.GOLD
    if elo >= 1000:
        return Tier.SILVER
    return Tier.BRONZE


# ── XP & Level System ──


def level_from_xp(xp: int) -> int:
    """Calculate agent level from total XP.

    Formula: level = floor(sqrt(xp / 100))
    Lv.1 = 0 XP, Lv.5 = 500 XP, Lv.10 = 2000 XP, Lv.20 = 10000 XP
    """
    if xp < 0:
        return 1
    return max(1, int(math.sqrt(xp / 100)))


def xp_for_level(level: int) -> int:
    """Calculate minimum XP required for a given level."""
    return int(math.pow(level, 2) * 100)


def xp_to_next_level(xp: int) -> int:
    """Calculate XP needed to reach the next level from current XP."""
    current_level = level_from_xp(xp)
    next_level_xp = xp_for_level(current_level + 1)
    return next_level_xp - xp


class XpSource(str, Enum):
    MATCH_WIN_BASELINE = "match_win_baseline"
    MATCH_WIN_PAIRWISE = "match_win_pairwise"
    STREAK_MILESTONE = "streak_milestone"
    ACHIEVEMENT_COMMON = "achievement_common"
    ACHIEVEMENT_RARE = "achievement_rare"
    ACHIEVEMENT_LEGENDARY = "achievement_legendary"
    TIER_PROMOTION = "tier_promotion"
    SHARPE_MASTER = "sharpe_master"
    DIAMOND_MAINTENANCE = "diamond_maintenance"
    MISSION_COMPLETE = "mission_complete"


XP_AMOUNTS: dict[XpSource, int] = {
    XpSource.MATCH_WIN_BASELINE: 10,
    XpSource.MATCH_WIN_PAIRWISE: 25,
    XpSource.STREAK_MILESTONE: 50,
    XpSource.ACHIEVEMENT_COMMON: 30,
    XpSource.ACHIEVEMENT_RARE: 75,
    XpSource.ACHIEVEMENT_LEGENDARY: 200,
    XpSource.TIER_PROMOTION: 100,
    XpSource.SHARPE_MASTER: 40,
    XpSource.DIAMOND_MAINTENANCE: 5,
    XpSource.MISSION_COMPLETE: 0,
}


class CompetitorCreate(BaseModel):
    type: CompetitorType
    name: str
    ref_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompetitorRecord(BaseModel):
    id: str
    type: CompetitorType
    name: str
    ref_id: str
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EloRating(BaseModel):
    competitor_id: str
    asset: str
    elo: int = 1000
    tier: Tier = Tier.SILVER
    matches_count: int = 0
    xp: int = 0


class CompetitorXP(BaseModel):
    """XP and level data for a competitor on a specific asset."""

    competitor_id: str
    asset: str
    xp: int = 0
    level: int = 1
    xp_to_next: int = 100

    @classmethod
    def from_xp(cls, competitor_id: str, asset: str, xp: int) -> "CompetitorXP":
        """Create CompetitorXP from raw XP value."""
        level = level_from_xp(xp)
        xp_to_next = xp_to_next_level(xp)
        return cls(
            competitor_id=competitor_id,
            asset=asset,
            xp=xp,
            level=level,
            xp_to_next=xp_to_next,
        )


class XpHistoryEntry(BaseModel):
    """Single XP award record."""

    id: str
    competitor_id: str
    asset: str
    source: XpSource
    amount: int
    created_at: datetime


class LeaderboardEntry(BaseModel):
    id: str
    type: CompetitorType
    name: str
    ref_id: str
    status: str
    elo: int
    tier: Tier
    matches_count: int
    streak: int = 0
    best_streak: int = 0
    xp: int = 0
    level: int = 1

    @classmethod
    def from_row(cls, row: dict) -> LeaderboardEntry:
        xp_val = row.get("xp", 0) or 0
        return cls(
            id=str(row["id"]),
            type=CompetitorType(row["type"]),
            name=row["name"],
            ref_id=row["ref_id"],
            status=row["status"],
            elo=row["elo"],
            tier=Tier(row["tier"]),
            matches_count=row["matches_count"],
            streak=row.get("current_streak", 0) or 0,
            best_streak=row.get("best_streak", 0) or 0,
            xp=xp_val,
            level=level_from_xp(xp_val),
        )


# ── Trait System ──

MAX_ACTIVE_TRAITS = 3


class AgentTrait(str, Enum):
    """Unlockable specialization traits for agents."""

    GENESIS = "genesis"
    RISK_MANAGER = "risk_manager"
    TAIL_HEDGED = "tail_hedged"
    TREND_FOLLOWER = "trend_follower"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    MEAN_REVERSION = "mean_reversion"
    RANGE_BOUND = "range_bound"
    STATISTICAL = "statistical"
    COINTEGRATION = "cointegration"
    KALMAN_FILTER = "kalman_filter"


# Level required to unlock each trait
TRAIT_REQUIREMENTS: dict[AgentTrait, int] = {
    AgentTrait.GENESIS: 0,
    AgentTrait.RISK_MANAGER: 5,
    AgentTrait.TREND_FOLLOWER: 5,
    AgentTrait.MEAN_REVERSION: 5,
    AgentTrait.TAIL_HEDGED: 10,
    AgentTrait.MOMENTUM: 10,
    AgentTrait.RANGE_BOUND: 10,
    AgentTrait.BREAKOUT: 15,
    AgentTrait.STATISTICAL: 15,
    AgentTrait.COINTEGRATION: 20,
    AgentTrait.KALMAN_FILTER: 25,
}

# Parent traits (for tree structure)
TRAIT_PARENTS: dict[AgentTrait, AgentTrait | None] = {
    AgentTrait.GENESIS: None,
    AgentTrait.RISK_MANAGER: AgentTrait.GENESIS,
    AgentTrait.TREND_FOLLOWER: AgentTrait.GENESIS,
    AgentTrait.MEAN_REVERSION: AgentTrait.GENESIS,
    AgentTrait.TAIL_HEDGED: AgentTrait.RISK_MANAGER,
    AgentTrait.MOMENTUM: AgentTrait.TREND_FOLLOWER,
    AgentTrait.BREAKOUT: AgentTrait.TREND_FOLLOWER,
    AgentTrait.RANGE_BOUND: AgentTrait.MEAN_REVERSION,
    AgentTrait.STATISTICAL: AgentTrait.MEAN_REVERSION,
    AgentTrait.COINTEGRATION: AgentTrait.STATISTICAL,
    AgentTrait.KALMAN_FILTER: AgentTrait.STATISTICAL,
}

# Trait display info
TRAIT_INFO: dict[AgentTrait, dict[str, str]] = {
    AgentTrait.GENESIS: {"icon": "🧬", "name": "Genesis", "effect": "Base agent type"},
    AgentTrait.RISK_MANAGER: {
        "icon": "🛡️",
        "name": "Risk Manager",
        "effect": "Volatility-targeting position sizing",
    },
    AgentTrait.TAIL_HEDGED: {
        "icon": "📉",
        "name": "Tail Hedged",
        "effect": "Can run with tail risk overlays",
    },
    AgentTrait.TREND_FOLLOWER: {
        "icon": "📈",
        "name": "Trend Follower",
        "effect": "Unlocks momentum strategies",
    },
    AgentTrait.MOMENTUM: {
        "icon": "🚀",
        "name": "Momentum",
        "effect": "Momentum signal generation",
    },
    AgentTrait.BREAKOUT: {
        "icon": "💥",
        "name": "Breakout",
        "effect": "Breakout detection",
    },
    AgentTrait.MEAN_REVERSION: {
        "icon": "↩️",
        "name": "Mean Reversion",
        "effect": "Unlocks mean-reversion strategies",
    },
    AgentTrait.RANGE_BOUND: {
        "icon": "📊",
        "name": "Range Bound",
        "effect": "Range-bound detection",
    },
    AgentTrait.STATISTICAL: {
        "icon": "📐",
        "name": "Statistical",
        "effect": "Statistical arbitrage",
    },
    AgentTrait.COINTEGRATION: {
        "icon": "🔗",
        "name": "Cointegration",
        "effect": "Pairs trading / cointegration",
    },
    AgentTrait.KALMAN_FILTER: {
        "icon": "⚙️",
        "name": "Kalman Filter",
        "effect": "Dynamic hedge ratios",
    },
}


class TraitUnlock(BaseModel):
    """Record of an unlocked trait for a competitor."""

    id: str
    competitor_id: str
    trait: AgentTrait
    unlocked_at: datetime
    unlocked_at_level: int


class TraitLoadout(BaseModel):
    """Active trait loadout for a competitor (max 3)."""

    competitor_id: str
    asset: str
    primary: AgentTrait | None = None
    secondary: AgentTrait | None = None
    tertiary: AgentTrait | None = None

    @property
    def active_traits(self) -> list[AgentTrait]:
        """Return list of non-None active traits."""
        return [
            t for t in [self.primary, self.secondary, self.tertiary] if t is not None
        ]

    def equip(self, trait: AgentTrait) -> bool:
        """Equip a trait in the first empty slot. Returns False if loadout full."""
        if self.primary is None:
            self.primary = trait
            return True
        if self.secondary is None:
            self.secondary = trait
            return True
        if self.tertiary is None:
            self.tertiary = trait
            return True
        return False

    def unequip(self, trait: AgentTrait) -> bool:
        """Remove a trait from the loadout. Returns True if found and removed."""
        if self.primary == trait:
            self.primary = None
            return True
        if self.secondary == trait:
            self.secondary = None
            return True
        if self.tertiary == trait:
            self.tertiary = None
            return True
        return False

    def swap(self, slot: str, trait: AgentTrait | None) -> None:
        """Swap a specific slot (primary/secondary/tertiary) to a new trait."""
        if slot == "primary":
            self.primary = trait
        elif slot == "secondary":
            self.secondary = trait
        elif slot == "tertiary":
            self.tertiary = trait


# ── Agent Card System ──


class CardRarity(str, Enum):
    """Card rarity levels based on achievement count."""

    COMMON = "common"  # 0-2 achievements
    UNCOMMON = "uncommon"  # 3-5 achievements
    RARE = "rare"  # 6-9 achievements
    EPIC = "epic"  # 10-14 achievements
    LEGENDARY = "legendary"  # 15+ achievements


# Rarity thresholds and styling
CARD_RARITY_THRESHOLDS: dict[CardRarity, int] = {
    CardRarity.COMMON: 0,
    CardRarity.UNCOMMON: 3,
    CardRarity.RARE: 6,
    CardRarity.EPIC: 10,
    CardRarity.LEGENDARY: 15,
}

CARD_RARITY_COLORS: dict[CardRarity, dict[str, str]] = {
    CardRarity.COMMON: {
        "border": "border-gray-600",
        "bg": "bg-gray-800/50",
        "glow": "",
        "text": "text-gray-300",
    },
    CardRarity.UNCOMMON: {
        "border": "border-green-600",
        "bg": "bg-green-950/30",
        "glow": "shadow-[0_0_15px_rgba(34,197,94,0.3)]",
        "text": "text-green-400",
    },
    CardRarity.RARE: {
        "border": "border-blue-500",
        "bg": "bg-blue-950/30",
        "glow": "shadow-[0_0_20px_rgba(59,130,246,0.4)]",
        "text": "text-blue-400",
    },
    CardRarity.EPIC: {
        "border": "border-purple-500",
        "bg": "bg-purple-950/30",
        "glow": "shadow-[0_0_25px_rgba(168,85,247,0.5)]",
        "text": "text-purple-400",
    },
    CardRarity.LEGENDARY: {
        "border": "border-amber-400",
        "bg": "bg-amber-950/30",
        "glow": "shadow-[0_0_30px_rgba(251,191,36,0.6)] animate-legendary-glow",
        "text": "text-amber-400",
    },
}


def card_rarity_for_achievements(achievement_count: int) -> CardRarity:
    """Determine card rarity based on achievement count."""
    if achievement_count >= 15:
        return CardRarity.LEGENDARY
    if achievement_count >= 10:
        return CardRarity.EPIC
    if achievement_count >= 6:
        return CardRarity.RARE
    if achievement_count >= 3:
        return CardRarity.UNCOMMON
    return CardRarity.COMMON


class CardStats(BaseModel):
    """Stats displayed on the agent card."""

    matches: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    current_streak: int = 0
    best_streak: int = 0
    total_xp: int = 0
    achievement_count: int = 0
    traits_unlocked: int = 0
    calibration_score: float = 0.0


class AgentCard(BaseModel):
    """Visual collectible card for an agent."""

    competitor_id: str
    name: str
    level: int
    tier: Tier
    elo: int
    rarity: CardRarity
    stats: CardStats

    # Visual elements
    trait_icons: list[str] = Field(default_factory=list)
    achievement_badges: list[dict[str, str]] = Field(default_factory=list)

    # Card metadata
    card_version: str = "1.0"
    generated_at: datetime | None = None


# ── Mission System ──

MISSION_XP_MULTIPLIER = 2.0


class MissionType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"


class MissionId(str, Enum):
    WARM_UP = "warm_up"
    STREAK_STARTER = "streak_starter"
    SHARPE_HUNTER = "sharpe_hunter"
    WEEKLY_GRIND = "weekly_grind"
    STREAK_MASTER = "streak_master"
    ACHIEVEMENT_HUNTER = "achievement_hunter"


MISSION_INFO: dict[MissionId, dict[str, Any]] = {
    MissionId.WARM_UP: {
        "type": MissionType.DAILY,
        "name": "Warm Up",
        "description": "Play 1 match",
        "target": 1,
        "xp_reward": 25,
        "icon": "🔥",
    },
    MissionId.STREAK_STARTER: {
        "type": MissionType.DAILY,
        "name": "Streak Starter",
        "description": "Win 3 matches",
        "target": 3,
        "xp_reward": 50,
        "icon": "⚡",
    },
    MissionId.SHARPE_HUNTER: {
        "type": MissionType.DAILY,
        "name": "Sharpe Hunter",
        "description": "Achieve Sharpe ratio > 1.5",
        "target": 1,
        "xp_reward": 75,
        "icon": "📈",
    },
    MissionId.WEEKLY_GRIND: {
        "type": MissionType.WEEKLY,
        "name": "Weekly Grind",
        "description": "Play 10 matches",
        "target": 10,
        "xp_reward": 100,
        "icon": "🎯",
    },
    MissionId.STREAK_MASTER: {
        "type": MissionType.WEEKLY,
        "name": "Streak Master",
        "description": "Achieve a 5 win streak",
        "target": 1,
        "xp_reward": 150,
        "icon": "🏆",
    },
    MissionId.ACHIEVEMENT_HUNTER: {
        "type": MissionType.WEEKLY,
        "name": "Achievement Hunter",
        "description": "Earn 3 achievements",
        "target": 3,
        "xp_reward": 200,
        "icon": "🎖️",
    },
}


class MissionProgress(BaseModel):
    id: str
    competitor_id: str
    mission_id: MissionId
    progress: int = 0
    target: int = 1
    completed: bool = False
    claimed: bool = False
    xp_awarded: int = 0
    period_start: datetime
    period_end: datetime
    updated_at: datetime | None = None

    @property
    def progress_pct(self) -> float:
        if self.target <= 0:
            return 100.0
        return min(100.0, (self.progress / self.target) * 100)

    @property
    def is_claimable(self) -> bool:
        return self.completed and not self.claimed


class MissionResponse(BaseModel):
    id: str
    mission_id: MissionId
    name: str
    description: str
    icon: str
    mission_type: MissionType
    progress: int
    target: int
    progress_pct: float
    completed: bool
    claimed: bool
    xp_reward: int
    is_claimable: bool
    period_end: datetime


SEASON_DURATION_DAYS = 90
ELO_SOFT_RESET_TARGET = 1000


class SeasonStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"
    UPCOMING = "upcoming"


class Season(BaseModel):
    id: str
    number: int
    name: str
    status: SeasonStatus
    started_at: datetime
    ends_at: datetime
    days_remaining: int
    total_participants: int = 0
    your_rank: int | None = None
    your_rating: int = 1000


class SeasonLeaderboardEntry(BaseModel):
    rank: int
    competitor_id: str
    name: str
    elo: int
    tier: Tier
    matches: int


class SeasonLeaderboard(BaseModel):
    season_id: str
    leaderboard: list[SeasonLeaderboardEntry]


class SeasonsResponse(BaseModel):
    current: Season | None
    seasons: list[Season]


MIN_BET_XP = 10
MAX_BET_XP = 1000
BETTING_HOUSE_CUT = 0.05


class BetStatus(str, Enum):
    OPEN = "open"
    LOCKED = "locked"
    SETTLED = "settled"
    CANCELLED = "cancelled"


class MatchBet(BaseModel):
    id: str
    match_id: str
    better_id: str
    predicted_winner: str
    amount: int
    potential_payout: int
    status: BetStatus = BetStatus.OPEN
    created_at: datetime | None = None
    settled_at: datetime | None = None
    payout: int = 0


class BettingPool(BaseModel):
    match_id: str
    total_pool: int = 0
    competitor_a_pool: int = 0
    competitor_b_pool: int = 0
    competitor_a_bettors: int = 0
    competitor_b_bettors: int = 0
    status: BetStatus = BetStatus.OPEN
    lock_time: datetime | None = None

    @property
    def competitor_a_odds(self) -> float:
        if self.competitor_a_pool == 0:
            return 0.5
        return self.competitor_a_pool / max(self.total_pool, 1)

    @property
    def competitor_b_odds(self) -> float:
        if self.competitor_b_pool == 0:
            return 0.5
        return self.competitor_b_pool / max(self.total_pool, 1)

    def calculate_payout(self, winner_pool: int, bet_amount: int) -> int:
        if winner_pool == 0:
            return 0
        house_cut = int(self.total_pool * BETTING_HOUSE_CUT)
        distributable = self.total_pool - house_cut
        return int((bet_amount / winner_pool) * distributable)


class BetPlacement(BaseModel):
    match_id: str
    predicted_winner: str
    amount: int


class BetResponse(BaseModel):
    id: str
    match_id: str
    predicted_winner: str
    amount: int
    potential_payout: int
    status: str
    created_at: str


class PoolResponse(BaseModel):
    match_id: str
    total_pool: int
    competitor_a_pool: int
    competitor_b_pool: int
    competitor_a_bettors: int
    competitor_b_bettors: int
    competitor_a_odds: float
    competitor_b_odds: float
    status: str


class BetResult(BaseModel):
    match_id: str
    winner: str
    total_pool: int
    house_cut: int
    distributed: int
    settled_bets: int


MUTATION_CHANCE_PER_LEVEL = 0.15
BREEDING_COOLDOWN_HOURS = 24


class MutationRarity(str, Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    LEGENDARY = "legendary"


class Mutation(BaseModel):
    id: str
    agent_id: str
    trait: AgentTrait
    rarity: MutationRarity
    bonus_multiplier: float
    level_obtained: int
    created_at: datetime | None = None


class AgentLineage(BaseModel):
    id: str
    agent_id: str
    parent_a_id: str | None = None
    parent_b_id: str | None = None
    generation: int = 0
    breeding_count: int = 0
    last_breed_at: datetime | None = None
    created_at: datetime | None = None


class BreedRequest(BaseModel):
    parent_a_id: str
    parent_b_id: str


class BreedResult(BaseModel):
    child_id: str
    child_name: str
    inherited_traits: list[AgentTrait]
    mutated_trait: AgentTrait | None = None
    mutation_rarity: MutationRarity | None = None
    generation: int


class MutationResponse(BaseModel):
    id: str
    trait: str
    rarity: str
    bonus_multiplier: float
    level_obtained: int


class LineageResponse(BaseModel):
    agent_id: str
    parent_a_id: str | None
    parent_b_id: str | None
    generation: int
    breeding_count: int
    can_breed: bool
    mutations: list[MutationResponse]
