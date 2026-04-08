# trading/competition/models.py
from __future__ import annotations

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

    @classmethod
    def from_row(cls, row: dict) -> LeaderboardEntry:
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
        )
