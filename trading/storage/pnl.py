from __future__ import annotations
from typing import Any

import aiosqlite


class TrackedPositionStore:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def open_position(
        self,
        *,
        agent_name: str,
        opportunity_id: str,
        symbol: str,
        side: str,
        entry_price: str,
        entry_quantity: int,
        entry_fees: str,
        entry_time: str,
        expires_at: str | None = None,
        broker_id: str | None = None,
        account_id: str | None = None,
    ) -> int:
        """INSERT a new position. Returns the lastrowid."""
        params = (
            agent_name,
            opportunity_id,
            symbol,
            side,
            entry_price,
            entry_quantity,
            entry_fees,
            entry_time,
            expires_at,
            broker_id,
            account_id,
        )
        if hasattr(self._db, "fetchone"):
            row = await self._db.fetchone(
                """INSERT INTO tracked_positions
                   (agent_name, opportunity_id, symbol, side, entry_price, entry_quantity, entry_fees, entry_time, expires_at, broker_id, account_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                params,
            )
            await self._db.commit()
            return int(row["id"]) if row else 0

        cursor = await self._db.execute(
            """INSERT INTO tracked_positions
               (agent_name, opportunity_id, symbol, side, entry_price, entry_quantity, entry_fees, entry_time, expires_at, broker_id, account_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            params,
        )
        await self._db.commit()
        return cursor.lastrowid

    async def close_position(
        self,
        position_id: int,
        *,
        exit_price: str,
        exit_fees: str,
        exit_time: str,
        exit_reason: str,
    ) -> None:
        """UPDATE position status to 'closed' with exit details."""
        await self._db.execute(
            """UPDATE tracked_positions
               SET exit_price = ?, exit_fees = ?, exit_time = ?, exit_reason = ?, status = 'closed'
               WHERE id = ?""",
            (exit_price, exit_fees, exit_time, exit_reason, position_id),
        )
        await self._db.commit()

    async def get(self, position_id: int) -> dict[str, Any] | None:
        """SELECT position by id."""
        async with self._db.execute(
            "SELECT * FROM tracked_positions WHERE id = ?", (position_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_open(
        self, agent_name: str | None = None, symbol: str | None = None
    ) -> list[dict[str, Any]]:
        """SELECT open positions with optional filters. ORDER BY entry_time ASC."""
        query = "SELECT * FROM tracked_positions WHERE status = 'open'"
        params: list[str | None] = []

        if agent_name is not None:
            query += " AND agent_name = ?"
            params.append(agent_name)

        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)

        query += " ORDER BY entry_time ASC"

        async with self._db.execute(query, params) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def list_closed(
        self, agent_name: str | None = None, limit: int = 100, since: str | None = None
    ) -> list[dict[str, Any]]:
        """SELECT closed positions with optional agent filter. ORDER BY exit_time DESC."""
        query = "SELECT * FROM tracked_positions WHERE status = 'closed'"
        params: list = []
        if agent_name is not None:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if since is not None:
            query += " AND exit_time >= ?"
            params.append(since)
        query += " ORDER BY exit_time DESC LIMIT ?"
        params.append(limit)
        async with self._db.execute(query, params) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def update_mae(self, position_id: int, mae: str) -> None:
        """UPDATE max_adverse_excursion."""
        await self._db.execute(
            "UPDATE tracked_positions SET max_adverse_excursion = ? WHERE id = ?",
            (mae, position_id),
        )
        await self._db.commit()

    async def get_open_quantity_by_symbol(self) -> dict[str, int]:
        """GROUP BY symbol, SUM(entry_quantity) for open positions."""
        async with self._db.execute(
            "SELECT symbol, SUM(entry_quantity) as total_quantity FROM tracked_positions WHERE status = 'open' GROUP BY symbol"
        ) as cursor:
            rows = await cursor.fetchall()
            return {row["symbol"]: row["total_quantity"] for row in rows}
