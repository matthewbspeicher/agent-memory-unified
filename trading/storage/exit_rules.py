"""Persistent store for position exit rules (SQLite)."""
from __future__ import annotations

import json
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class ExitRuleStore:
    """Persist and retrieve exit rule serialisations for positions."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def save(self, position_id: int, rules: list[dict[str, Any]]) -> None:
        """Insert or replace the exit rules for a position."""
        rules_json = json.dumps(rules)
        await self._db.execute(
            """
            INSERT OR REPLACE INTO position_exit_rules (position_id, rules_json)
            VALUES (?, ?)
            """,
            (position_id, rules_json),
        )
        await self._db.commit()

    async def delete(self, position_id: int) -> None:
        """Remove the exit rules for a position."""
        await self._db.execute(
            "DELETE FROM position_exit_rules WHERE position_id = ?",
            (position_id,),
        )
        await self._db.commit()

    async def load_all(self) -> dict[int, list[dict[str, Any]]]:
        """Load all persisted rules — used to restore in-memory state on startup."""
        async with self._db.execute(
            "SELECT position_id, rules_json FROM position_exit_rules"
        ) as cursor:
            rows = await cursor.fetchall()
            return {
                int(row["position_id"]): json.loads(row["rules_json"])
                for row in rows
            }
