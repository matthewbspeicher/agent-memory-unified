# trading/competition/store.py
"""Competition store -- DB access layer using raw asyncpg SQL."""

from __future__ import annotations

import json
import logging
import uuid
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
        raw_id = f"{competitor.type.value}:{competitor.ref_id}"
        comp_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, raw_id))
        sql = """
            INSERT INTO competitors (id, type, name, ref_id, metadata)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (type, ref_id) DO UPDATE
                SET name = EXCLUDED.name,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """
        params = [
            comp_id,
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
        sql = "SELECT * FROM competitors WHERE id = ?"
        async with self._db.execute(sql, [competitor_id]) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return _row_to_competitor(row)

    async def get_competitor_by_ref(
        self, comp_type: CompetitorType, ref_id: str
    ) -> CompetitorRecord | None:
        """Look up a competitor by (type, ref_id) unique key."""
        sql = "SELECT * FROM competitors WHERE type = ? AND ref_id = ?"
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
            sql = "SELECT * FROM competitors WHERE status = 'active' AND type = ? ORDER BY name"
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
        elo_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{competitor_id}:{asset}"))
        sql = """
            INSERT INTO elo_ratings (id, competitor_id, asset)
            VALUES (?, ?, ?)
            ON CONFLICT (competitor_id, asset) DO NOTHING
        """
        await self._db.execute(sql, [elo_id, competitor_id, asset])

    async def get_elo(self, competitor_id: str, asset: str) -> int:
        """Return the current ELO for a competitor+asset (default 1000)."""
        sql = "SELECT elo FROM elo_ratings WHERE competitor_id = ? AND asset = ?"
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
            SET elo = ?, tier = ?, matches_count = matches_count + 1, updated_at = CURRENT_TIMESTAMP
            WHERE competitor_id = ? AND asset = ?
        """
        await self._db.execute(update_sql, [new_elo, tier.value, competitor_id, asset])

        elo_hist_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_DNS, f"{competitor_id}:{asset}:{new_elo}:{elo_delta}"
            )
        )
        history_sql = """
            INSERT INTO elo_history (id, competitor_id, asset, elo, tier, elo_delta)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        await self._db.execute(
            history_sql,
            [elo_hist_id, competitor_id, asset, new_elo, tier.value, elo_delta],
        )

    async def get_elo_history(
        self, competitor_id: str, asset: str, days: int = 30
    ) -> list[dict]:
        """Return recent ELO history entries."""
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        sql = """
            SELECT elo, tier, elo_delta, recorded_at
            FROM elo_history
            WHERE competitor_id = ?
              AND asset = ?
              AND recorded_at >= ?
            ORDER BY recorded_at DESC
        """
        async with self._db.execute(sql, [competitor_id, asset, cutoff]) as cur:
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
                JOIN elo_ratings e ON e.competitor_id = c.id AND e.asset = ?
                LEFT JOIN streaks s ON s.competitor_id = c.id
                    AND s.asset = ? AND s.streak_type = 'win'
                WHERE c.status = 'active' AND c.type = ?
                ORDER BY e.elo DESC
                LIMIT ? OFFSET ?
            """
            params: list[Any] = [asset, comp_type.value, limit, offset]
        else:
            sql = """
                SELECT c.id, c.type, c.name, c.ref_id, c.status,
                       e.elo, e.tier, e.matches_count,
                       COALESCE(s.current_count, 0) AS current_streak,
                       COALESCE(s.best_count, 0) AS best_streak
                FROM competitors c
                JOIN elo_ratings e ON e.competitor_id = c.id AND e.asset = ?
                LEFT JOIN streaks s ON s.competitor_id = c.id
                    AND s.asset = ? AND s.streak_type = 'win'
                WHERE c.status = 'active'
                ORDER BY e.elo DESC
                LIMIT ? OFFSET ?
            """
            params = [asset, asset, limit, offset]

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

    async def get_recent_achievements(
        self, since_id: int = 0, limit: int = 10
    ) -> list[dict]:
        """Get recent achievements for SSE feed."""
        sql = """
            SELECT a.id, a.competitor_id, a.achievement_type, a.earned_at,
                   c.name, c.type
            FROM achievements a
            JOIN competitors c ON c.id = a.competitor_id
            WHERE a.id > ?
            ORDER BY a.earned_at ASC
            LIMIT ?
        """
        async with self._db.execute(sql, [since_id, limit]) as cur:
            rows = await cur.fetchall()
        return [
            {
                "id": row["id"],
                "competitor": row["name"],
                "competitor_type": row["type"],
                "type": row["achievement_type"],
                "earned_at": str(row["earned_at"]),
            }
            for row in rows
        ]

    async def get_competitor_calibration(
        self, competitor_id: str, asset: str = "BTC"
    ) -> float:
        """Get calibration score for a competitor (0.0-1.0)."""
        sql = """
            SELECT calibration_score
            FROM elo_ratings
            WHERE competitor_id = ? AND asset = ?
        """
        async with self._db.execute(sql, [competitor_id, asset]) as cur:
            row = await cur.fetchone()
        if row:
            return float(row.get("calibration_score", 0.85))
        return 0.85  # Default

    async def get_head_to_head(
        self, competitor_a: str, competitor_b: str, asset: str = "BTC"
    ) -> dict:
        """Return head-to-head win/loss/draw stats between two competitors."""
        sql = """
            SELECT
                COUNT(*) FILTER (WHERE winner_id = ?) AS wins_a,
                COUNT(*) FILTER (WHERE winner_id = ?) AS wins_b,
                COUNT(*) FILTER (WHERE winner_id IS NULL) AS draws,
                COUNT(*) AS total
            FROM matches
            WHERE ((competitor_a_id = ? AND competitor_b_id = ?)
                OR (competitor_a_id = ? AND competitor_b_id = ?))
                AND asset = ?
                AND match_type = 'pairwise'
        """
        async with self._db.execute(sql, [competitor_a, competitor_b, asset]) as cur:
            row = await cur.fetchone()
        return row or {"wins_a": 0, "wins_b": 0, "draws": 0, "total": 0}

    async def record_match(self, match_data: dict) -> None:
        """Record a match result in the matches table."""
        sql = """
            INSERT INTO matches (
                competitor_a_id, competitor_b_id, asset, time_window,
                winner_id, score_a, score_b, elo_delta_a, elo_delta_b, match_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
