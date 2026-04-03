from __future__ import annotations

import json
from typing import Any

import aiosqlite


class AgentOverrideStore:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get(self, agent_name: str) -> dict[str, Any] | None:
        """Get override for an agent."""
        cursor = await self._db.execute(
            "SELECT * FROM agent_overrides WHERE agent_name = ?",
            (agent_name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def get_all(self) -> list[dict[str, Any]]:
        """Get all overrides."""
        cursor = await self._db.execute(
            "SELECT * FROM agent_overrides ORDER BY updated_at DESC"
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def set_trust_level(self, agent_name: str, trust_level: str) -> None:
        """Upsert trust level override."""
        await self._db.execute(
            """INSERT INTO agent_overrides (agent_name, trust_level, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(agent_name) DO UPDATE SET
               trust_level = excluded.trust_level,
               updated_at = datetime('now')""",
            (agent_name, trust_level),
        )
        await self._db.commit()

    async def set_runtime_parameters(self, agent_name: str, params: dict[str, Any]) -> None:
        """Upsert runtime parameters as JSON."""
        await self._db.execute(
            """INSERT INTO agent_overrides (agent_name, runtime_parameters, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(agent_name) DO UPDATE SET
               runtime_parameters = excluded.runtime_parameters,
               updated_at = datetime('now')""",
            (agent_name, json.dumps(params)),
        )
        await self._db.commit()

    async def delete(self, agent_name: str) -> None:
        """Delete an override."""
        await self._db.execute(
            "DELETE FROM agent_overrides WHERE agent_name = ?",
            (agent_name,),
        )
        await self._db.commit()

    async def log_trust_change(
        self, agent_name: str, old_level: str, new_level: str, changed_by: str
    ) -> None:
        """Insert trust change event into trust_events table."""
        await self._db.execute(
            """INSERT INTO trust_events (agent_name, old_level, new_level, changed_by, changed_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (agent_name, old_level, new_level, changed_by),
        )
        await self._db.commit()

    async def get_trust_history(self, agent_name: str, limit: int = 50) -> list[dict[str, Any]]:
        """Query trust_events for an agent."""
        cursor = await self._db.execute(
            "SELECT * FROM trust_events WHERE agent_name = ? ORDER BY changed_at DESC LIMIT ?",
            (agent_name, limit),
        )
        return [dict(row) for row in await cursor.fetchall()]
