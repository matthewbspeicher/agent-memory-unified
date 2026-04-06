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
