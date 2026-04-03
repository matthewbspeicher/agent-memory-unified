from __future__ import annotations

from datetime import datetime

import aiosqlite


class ConsensusStore:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def add_vote(
        self,
        symbol: str,
        side: str,
        agent_name: str,
        opportunity_id: str,
        voted_at: datetime,
    ) -> None:
        await self._db.execute(
            """INSERT OR REPLACE INTO consensus_votes
               (symbol, side, agent_name, opportunity_id, voted_at)
               VALUES (?, ?, ?, ?, ?)""",
            (symbol, side, agent_name, opportunity_id, voted_at.isoformat()),
        )
        await self._db.commit()

    async def get_votes(self, symbol: str, side: str, cutoff: datetime) -> list[dict]:
        cursor = await self._db.execute(
            """SELECT symbol, side, agent_name, opportunity_id, voted_at
               FROM consensus_votes
               WHERE symbol = ? AND side = ? AND voted_at >= ?""",
            (symbol, side, cutoff.isoformat()),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def clear_votes(self, symbol: str, side: str) -> None:
        await self._db.execute(
            "DELETE FROM consensus_votes WHERE symbol = ? AND side = ?",
            (symbol, side),
        )
        await self._db.commit()

    async def cleanup_expired(self, cutoff: datetime) -> None:
        await self._db.execute(
            "DELETE FROM consensus_votes WHERE voted_at < ?",
            (cutoff.isoformat(),),
        )
        await self._db.commit()
