# tests/unit/competition/test_models.py
from __future__ import annotations

import pytest
from competition.models import (
    CompetitorCreate,
    CompetitorRecord,
    CompetitorType,
    EloRating,
    LeaderboardEntry,
    Tier,
    tier_for_elo,
)


class TestTierForElo:
    def test_diamond(self):
        assert tier_for_elo(1400) == Tier.DIAMOND
        assert tier_for_elo(1500) == Tier.DIAMOND

    def test_gold(self):
        assert tier_for_elo(1200) == Tier.GOLD
        assert tier_for_elo(1399) == Tier.GOLD

    def test_silver(self):
        assert tier_for_elo(1000) == Tier.SILVER
        assert tier_for_elo(1199) == Tier.SILVER

    def test_bronze(self):
        assert tier_for_elo(999) == Tier.BRONZE
        assert tier_for_elo(0) == Tier.BRONZE


class TestCompetitorCreate:
    def test_valid_agent(self):
        c = CompetitorCreate(
            type=CompetitorType.AGENT, name="rsi_scanner", ref_id="rsi_scanner"
        )
        assert c.type == CompetitorType.AGENT
        assert c.name == "rsi_scanner"

    def test_valid_miner(self):
        c = CompetitorCreate(
            type=CompetitorType.MINER,
            name="miner_5DkVM...",
            ref_id="5DkVM4wyv4ZXGvb9ZmYafPiySbmWS4s2i5W37CNHuh4ggAha",
            metadata={"uid": 144},
        )
        assert c.metadata == {"uid": 144}

    def test_valid_provider(self):
        c = CompetitorCreate(
            type=CompetitorType.PROVIDER, name="sentiment", ref_id="sentiment"
        )
        assert c.type == CompetitorType.PROVIDER


class TestLeaderboardEntry:
    def test_from_row(self):
        row = {
            "id": "abc-123",
            "type": "agent",
            "name": "rsi_scanner",
            "ref_id": "rsi_scanner",
            "status": "active",
            "elo": 1250,
            "tier": "gold",
            "matches_count": 42,
            "current_streak": 5,
            "best_streak": 8,
        }
        entry = LeaderboardEntry.from_row(row)
        assert entry.elo == 1250
        assert entry.tier == Tier.GOLD
        assert entry.streak == 5
