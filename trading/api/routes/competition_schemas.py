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
