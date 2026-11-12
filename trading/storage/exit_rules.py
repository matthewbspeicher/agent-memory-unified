"""Persistent store for position exit rules (SQLite)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class ExitRuleStore:
    """Persist and retrieve exit rule serialisations for positions."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        self._sync_store = None
        self._sync_lock = asyncio.Lock()
        self._closed = False

    async def close(self) -> None:
        async with self._sync_lock:
            if self._sync_store is not None:
                await self._sync_store.close()
            self._closed = True

    async def sync_position(
        self, position_id: int, rules: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        """Atomically reconcile protection against the current durable position.

        A dedicated file connection prevents committing another store's work.
        Memory databases must be supplied without an unrelated transaction.
        """
        from storage.unit_of_work import UnitOfWork

        async with self._sync_lock:
            if self._closed:
                raise RuntimeError("ExitRuleStore is closed")
            if self._sync_store is None:
                # Assign only once adoption succeeded, so a failure is retried
                # rather than leaving this store on the shared connection.
                sync_store = UnitOfWork(self._db)
                await sync_store.adopt_dedicated_connection(busy_timeout=True)
                self._sync_store = sync_store
            async with self._sync_store.transaction() as db:
                row = await (await db.execute(
                    "SELECT status FROM tracked_positions WHERE id = ?", (position_id,)
                )).fetchone()
                if row is None or row["status"] != "open":
                    await db.execute(
                        "DELETE FROM position_exit_rules WHERE position_id = ?",
                        (position_id,),
                    )
                    return None
                await db.execute(
                    "INSERT INTO position_exit_rules (position_id, rules_json) VALUES (?, ?) "
                    "ON CONFLICT(position_id) DO NOTHING",
                    (position_id, json.dumps(rules)),
                )
                row = await (await db.execute(
                    "SELECT rules_json FROM position_exit_rules WHERE position_id = ?",
                    (position_id,),
                )).fetchone()
                persisted = json.loads(row["rules_json"])
                if not isinstance(persisted, list):
                    raise ValueError("Persisted exit rules must be a list")
                return persisted

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

    async def ensure(
        self, position_id: int, rules: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Atomically retain initial rules and return the durable winning value."""
        await self._db.execute(
            "INSERT INTO position_exit_rules (position_id, rules_json) VALUES (?, ?) "
            "ON CONFLICT(position_id) DO NOTHING",
            (position_id, json.dumps(rules)),
        )
        await self._db.commit()
        async with self._db.execute(
            "SELECT rules_json FROM position_exit_rules WHERE position_id = ?",
            (position_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Exit rules were removed while being initialized")
        persisted = json.loads(row["rules_json"])
        if not isinstance(persisted, list):
            raise ValueError("Persisted exit rules must be a list")
        return persisted

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
                int(row["position_id"]): json.loads(row["rules_json"]) for row in rows
            }
