# trading/competition/store.py
"""Competition store -- DB access layer using raw asyncpg SQL."""

from __future__ import annotations

import json
import logging
from typing import Any

from competition.models import (
    CompetitorCreate,
    CompetitorRecord,
    CompetitorType,
    EloRating,
    LeaderboardEntry,
    Tier,
    tier_for_elo,
)

logger = logging.getLogger(__name__)


class CompetitionStore:
    """Persistence layer for the Arena Alpha competition system."""

    def __init__(self, db: Any) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Competitors
    # ------------------------------------------------------------------

    async def upsert_competitor(self, competitor: CompetitorCreate) -> str:
        """Insert or update a competitor.  Returns the competitor id."""
        sql = """
            INSERT INTO competitors (type, name, ref_id, metadata)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (type, ref_id) DO UPDATE
                SET name = EXCLUDED.name,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
            RETURNING id
        """
        params = [
            competitor.type.value,
            competitor.name,
            competitor.ref_id,
            json.dumps(competitor.metadata),
        ]
        async with self._db.execute(sql, params) as cur:
            row = await cur.fetchone()
        return str(row["id"]) if row else ""

    async def get_competitor(self, competitor_id: str) -> CompetitorRecord | None:
        """Look up a competitor by primary key."""
        sql = "SELECT * FROM competitors WHERE id = $1"
        async with self._db.execute(sql, [competitor_id]) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return _row_to_competitor(row)

    async def get_competitor_by_ref(
        self, comp_type: CompetitorType, ref_id: str
    ) -> CompetitorRecord | None:
        """Look up a competitor by (type, ref_id) unique key."""
        sql = "SELECT * FROM competitors WHERE type = $1 AND ref_id = $2"
        async with self._db.execute(sql, [comp_type.value, ref_id]) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return _row_to_competitor(row)

    async def list_competitors(
        self, comp_type: CompetitorType | None = None
    ) -> list[CompetitorRecord]:
        """List active competitors, optionally filtered by type."""
        if comp_type is not None:
            sql = "SELECT * FROM competitors WHERE status = 'active' AND type = $1 ORDER BY name"
            params: list[Any] = [comp_type.value]
        else:
            sql = "SELECT * FROM competitors WHERE status = 'active' ORDER BY name"
            params = []
        async with self._db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [_row_to_competitor(r) for r in rows]

    # ------------------------------------------------------------------
    # ELO Ratings
    # ------------------------------------------------------------------

    async def ensure_elo_rating(self, competitor_id: str, asset: str) -> None:
        """Create an ELO rating row if it does not exist."""
        sql = """
            INSERT INTO elo_ratings (competitor_id, asset)
            VALUES ($1, $2)
            ON CONFLICT (competitor_id, asset) DO NOTHING
        """
        await self._db.execute(sql, [competitor_id, asset])

    async def get_elo(self, competitor_id: str, asset: str) -> int:
        """Return the current ELO for a competitor+asset (default 1000)."""
        sql = "SELECT elo FROM elo_ratings WHERE competitor_id = $1 AND asset = $2"
        async with self._db.execute(sql, [competitor_id, asset]) as cur:
            row = await cur.fetchone()
        return row["elo"] if row else 1000

    async def update_elo(
        self,
        competitor_id: str,
        asset: str,
        new_elo: int,
        elo_delta: int,
    ) -> None:
        """Update the live ELO rating and append a history record."""
        tier = tier_for_elo(new_elo)
        update_sql = """
            UPDATE elo_ratings
            SET elo = $1, tier = $2, matches_count = matches_count + 1, updated_at = NOW()
            WHERE competitor_id = $3 AND asset = $4
        """
        await self._db.execute(update_sql, [new_elo, tier.value, competitor_id, asset])

        history_sql = """
            INSERT INTO elo_history (competitor_id, asset, elo, tier, elo_delta)
            VALUES ($1, $2, $3, $4, $5)
        """
        await self._db.execute(
            history_sql, [competitor_id, asset, new_elo, tier.value, elo_delta]
        )

    async def get_elo_history(
        self, competitor_id: str, asset: str, days: int = 30
    ) -> list[dict]:
        """Return recent ELO history entries."""
        sql = """
            SELECT elo, tier, elo_delta, recorded_at
            FROM elo_history
            WHERE competitor_id = $1
              AND asset = $2
              AND recorded_at >= NOW() - CAST($3 || ' days' AS INTERVAL)
            ORDER BY recorded_at DESC
        """
        async with self._db.execute(sql, [competitor_id, asset, str(days)]) as cur:
            rows = await cur.fetchall()
        return rows

    # ------------------------------------------------------------------
    # Leaderboard
    # ------------------------------------------------------------------

    async def get_leaderboard(
        self,
        asset: str,
        comp_type: CompetitorType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LeaderboardEntry]:
        """Fetch the leaderboard for a given asset, ordered by ELO desc."""
        if comp_type is not None:
            sql = """
                SELECT c.id, c.type, c.name, c.ref_id, c.status,
                       e.elo, e.tier, e.matches_count,
                       COALESCE(s.current_count, 0) AS current_streak,
                       COALESCE(s.best_count, 0) AS best_streak
                FROM competitors c
                JOIN elo_ratings e ON e.competitor_id = c.id AND e.asset = $1
                LEFT JOIN streaks s ON s.competitor_id = c.id
                    AND s.asset = $1 AND s.streak_type = 'win'
                WHERE c.status = 'active' AND c.type = $2
                ORDER BY e.elo DESC
                LIMIT $3 OFFSET $4
            """
            params: list[Any] = [asset, comp_type.value, limit, offset]
        else:
            sql = """
                SELECT c.id, c.type, c.name, c.ref_id, c.status,
                       e.elo, e.tier, e.matches_count,
                       COALESCE(s.current_count, 0) AS current_streak,
                       COALESCE(s.best_count, 0) AS best_streak
                FROM competitors c
                JOIN elo_ratings e ON e.competitor_id = c.id AND e.asset = $1
                LEFT JOIN streaks s ON s.competitor_id = c.id
                    AND s.asset = $1 AND s.streak_type = 'win'
                WHERE c.status = 'active'
                ORDER BY e.elo DESC
                LIMIT $2 OFFSET $3
            """
            params = [asset, limit, offset]

        async with self._db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [LeaderboardEntry.from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Dashboard summary
    # ------------------------------------------------------------------

    async def get_dashboard_summary(self, asset: str) -> dict:
        """Return a summary dict suitable for the frontend dashboard."""
        entries = await self.get_leaderboard(asset=asset)
        return {
            "asset": asset,
            "total_competitors": len(entries),
            "leaderboard": [e.model_dump() for e in entries],
        }

    async def record_match(self, match_data: dict) -> None:
        """Record a match result in the matches table."""
        sql = """
            INSERT INTO matches (
                competitor_a_id, competitor_b_id, asset, window,
                winner_id, score_a, score_b, elo_delta_a, elo_delta_b, match_type
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """
        await self._db.execute(
            sql,
            [
                match_data.get("competitor_a_id"),
                match_data.get("competitor_b_id"),
                match_data.get("asset", "BTC"),
                match_data.get("window", "5m"),
                match_data.get("winner_id"),
                match_data.get("score_a", 0),
                match_data.get("score_b", 0),
                match_data.get("elo_delta_a", 0),
                match_data.get("elo_delta_b", 0),
                match_data.get("match_type", "baseline"),
            ],
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _row_to_competitor(row: dict) -> CompetitorRecord:
    meta = row.get("metadata", {})
    if isinstance(meta, str):
        meta = json.loads(meta)
    return CompetitorRecord(
        id=str(row["id"]),
        type=CompetitorType(row["type"]),
        name=row["name"],
        ref_id=row["ref_id"],
        status=row.get("status", "active"),
        metadata=meta,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )
