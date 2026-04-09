from __future__ import annotations
from typing import Any


class TournamentStore:
    def __init__(self, db: Any) -> None:
        self._db = db

    async def get_stage(self, agent_name: str) -> int:
        cursor = await self._db.execute(
            "SELECT current_stage FROM agent_stages WHERE agent_name = ?",
            (agent_name,),
        )
        row = await cursor.fetchone()
        return int(row["current_stage"]) if row else 0

    async def set_stage(self, agent_name: str, stage: int) -> None:
        await self._db.execute(
            """
            INSERT INTO agent_stages (agent_name, current_stage, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(agent_name) DO UPDATE SET
                current_stage = excluded.current_stage,
                updated_at = excluded.updated_at
            """,
            (agent_name, stage),
        )
        await self._db.commit()

    async def get_all_stages(self) -> dict[str, int]:
        cursor = await self._db.execute(
            "SELECT agent_name, current_stage FROM agent_stages"
        )
        rows = await cursor.fetchall()
        return {row["agent_name"]: int(row["current_stage"]) for row in rows}

    async def write_audit(
        self,
        *,
        agent_name: str,
        from_stage: int,
        to_stage: int,
        reason: str,
        ai_analysis: str,
        ai_recommendation: str,
        overridden_by: str | None,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO tournament_audit_log
                (agent_name, from_stage, to_stage, reason, ai_analysis, ai_recommendation, overridden_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_name,
                from_stage,
                to_stage,
                reason,
                ai_analysis,
                ai_recommendation,
                overridden_by,
            ),
        )
        await self._db.commit()

    async def list_audit(self, limit: int = 50) -> list[dict]:
        cursor = await self._db.execute(
            """
            SELECT id, agent_name, from_stage, to_stage, reason,
                   ai_analysis, ai_recommendation, timestamp, overridden_by
            FROM tournament_audit_log
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ── ELO Rating Storage ──────────────────────────────────────────────────

    async def get_elo(self, agent_name: str) -> int:
        """Get current ELO rating for an agent (default: 1000)."""
        cursor = await self._db.execute(
            "SELECT elo_rating FROM agent_elo_ratings WHERE agent_name = ?",
            (agent_name,),
        )
        row = await cursor.fetchone()
        return int(row["elo_rating"]) if row else 1000

    async def set_elo(self, agent_name: str, elo_rating: int) -> None:
        """Update ELO rating for an agent."""
        await self._db.execute(
            """
            INSERT INTO agent_elo_ratings (agent_name, elo_rating, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(agent_name) DO UPDATE SET
                elo_rating = excluded.elo_rating,
                updated_at = excluded.updated_at
            """,
            (agent_name, elo_rating),
        )
        await self._db.commit()

    async def get_all_elo(self) -> dict[str, int]:
        """Get ELO ratings for all agents."""
        cursor = await self._db.execute(
            "SELECT agent_name, elo_rating FROM agent_elo_ratings"
        )
        rows = await cursor.fetchall()
        return {row["agent_name"]: int(row["elo_rating"]) for row in rows}

    async def get_elo_history(self, agent_name: str, limit: int = 20) -> list[dict]:
        """Get ELO rating history for an agent."""
        cursor = await self._db.execute(
            """
            SELECT agent_name, old_rating, new_rating, reason, delta, timestamp
            FROM elo_rating_history
            WHERE agent_name = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (agent_name, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def record_elo_change(
        self,
        agent_name: str,
        old_rating: int,
        new_rating: int,
        reason: str,
    ) -> None:
        """Record an ELO rating change for audit trail."""
        delta = new_rating - old_rating
        await self._db.execute(
            """
            INSERT INTO elo_rating_history
                (agent_name, old_rating, new_rating, reason, delta, timestamp)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (agent_name, old_rating, new_rating, reason, delta),
        )
