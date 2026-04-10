# trading/api/routes/competition_schemas.py
from __future__ import annotations

from pydantic import BaseModel, Field


class CompetitorResponse(BaseModel):
    id: str
    type: str
    name: str
    ref_id: str
    status: str
    elo: int
    tier: str
    matches_count: int
    streak: int = 0
    best_streak: int = 0
    xp: int = 0
    level: int = 1


class LeaderboardResponse(BaseModel):
    leaderboard: list[CompetitorResponse]
    competitor_count: int


class DashboardSummaryResponse(BaseModel):
    leaderboard: list[CompetitorResponse]
    competitor_count: int


class EloHistoryPoint(BaseModel):
    elo: int
    tier: str
    elo_delta: int
    recorded_at: str


class EloHistoryResponse(BaseModel):
    competitor_id: str
    asset: str
    history: list[EloHistoryPoint]


class CompetitorDetailResponse(BaseModel):
    id: str
    type: str
    name: str
    ref_id: str
    status: str
    metadata: dict = Field(default_factory=dict)
    ratings: dict[str, dict] = Field(default_factory=dict)
    calibration_score: float = 0.85


# ── XP & Level Response Types ──


class XpHistoryPoint(BaseModel):
    id: str
    source: str
    amount: int
    created_at: str


class XpResponse(BaseModel):
    competitor_id: str
    asset: str
    xp: int
    level: int
    xp_to_next_level: int


class XpHistoryResponse(BaseModel):
    competitor_id: str
    asset: str
    history: list[XpHistoryPoint]


# ── Trait Response Types ──


class TraitInfo(BaseModel):
    trait: str
    icon: str
    name: str
    effect: str
    required_level: int
    parent: str | None = None


class TraitUnlockResponse(BaseModel):
    trait: str
    unlocked_at: str
    unlocked_at_level: int


class UnlockedTraitsResponse(BaseModel):
    competitor_id: str
    unlocked_traits: list[str]
    trait_tree: list[TraitInfo]


class TraitLoadoutResponse(BaseModel):
    competitor_id: str
    asset: str
    primary: str | None = None
    secondary: str | None = None
    tertiary: str | None = None


class EquipTraitRequest(BaseModel):
    trait: str


class EquipTraitResponse(BaseModel):
    loadout: TraitLoadoutResponse
    equipped: bool
    message: str | None = None


# ── Agent Card Response Types ──


class CardStatsResponse(BaseModel):
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


class AgentCardResponse(BaseModel):
    competitor_id: str
    name: str
    level: int
    tier: str
    elo: int
    rarity: str
    stats: CardStatsResponse
    trait_icons: list[str] = Field(default_factory=list)
    achievement_badges: list[dict[str, str]] = Field(default_factory=list)
    card_version: str = "1.0"


class MissionResponse(BaseModel):
    id: str
    mission_id: str
    name: str
    description: str
    icon: str
    mission_type: str
    progress: int
    target: int
    progress_pct: float
    completed: bool
    claimed: bool
    xp_reward: int
    is_claimable: bool
    period_end: str


class MissionsResponse(BaseModel):
    missions: list[MissionResponse]


class ClaimMissionResponse(BaseModel):
    success: bool
    xp_awarded: int
    message: str


class SeasonResponse(BaseModel):
    id: str
    number: int
    name: str
    status: str
    started_at: str
    ends_at: str
    days_remaining: int
    total_participants: int
    your_rank: int | None
    your_rating: int


class SeasonLeaderboardEntry(BaseModel):
    rank: int
    competitor_id: str
    name: str
    elo: int
    tier: str
    matches: int


class SeasonLeaderboardResponse(BaseModel):
    season_id: str
    leaderboard: list[SeasonLeaderboardEntry]


class SeasonsResponse(BaseModel):
    current: SeasonResponse | None
    seasons: list[SeasonResponse]


class FleetStats(BaseModel):
    total_agents: int
    avg_level: int
    total_xp: int
    total_matches: int
    avg_elo: int
    legendary_count: int
    mission_claimable: int


class FleetResponse(BaseModel):
    stats: FleetStats
    cards: list[AgentCardResponse]


class BetPlacement(BaseModel):
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


class BetResultResponse(BaseModel):
    match_id: str
    winner: str
    total_pool: int
    house_cut: int
    distributed: int
    settled_bets: int


class BreedRequest(BaseModel):
    parent_a_id: str
    parent_b_id: str
    child_name: str


class MutationResponse(BaseModel):
    id: str
    trait: str
    rarity: str
    bonus_multiplier: float
    level_obtained: int


class BreedResultResponse(BaseModel):
    child_id: str
    child_name: str
    inherited_traits: list[str]
    mutated_trait: str | None
    mutation_rarity: str | None
    generation: int


class LineageResponse(BaseModel):
    agent_id: str
    parent_a_id: str | None
    parent_b_id: str | None
    generation: int
    breeding_count: int
    can_breed: bool
    mutations: list[MutationResponse]
