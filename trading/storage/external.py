from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import aiosqlite


class ExternalPortfolioStore:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def import_positions(
        self,
        broker: str,
        account_id: str,
        account_name: str,
        positions: list[dict],
        balance: dict,
    ) -> None:
        imported_at = datetime.now(timezone.utc).isoformat()
        async with self._db.execute("BEGIN"):
            pass
        await self._db.execute(
            "DELETE FROM external_positions WHERE broker = ? AND account_id = ?",
            (broker, account_id),
        )
        await self._db.execute(
            "DELETE FROM external_balances WHERE broker = ? AND account_id = ?",
            (broker, account_id),
        )
        for pos in positions:
            await self._db.execute(
                """
                INSERT INTO external_positions
                    (broker, account_id, account_name, symbol, description,
                     quantity, cost_basis, current_value, last_price, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    broker,
                    account_id,
                    account_name,
                    pos["symbol"],
                    pos.get("description", ""),
                    str(pos["quantity"]),
                    str(pos["cost_basis"])
                    if pos.get("cost_basis") is not None
                    else None,
                    str(pos["current_value"]),
                    str(pos["last_price"]),
                    imported_at,
                ),
            )
        await self._db.execute(
            """
            INSERT INTO external_balances
                (broker, account_id, account_name, net_liquidation, cash, imported_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                broker,
                account_id,
                account_name,
                str(balance["net_liquidation"]),
                str(balance.get("cash", "0")),
                imported_at,
            ),
        )
        await self._db.commit()

    async def get_positions(
        self,
        broker: str | None = None,
        account_id: str | None = None,
        exclude_accounts: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list = []
        if broker is not None:
            where.append("broker = ?")
            params.append(broker)
        if account_id is not None:
            where.append("account_id = ?")
            params.append(account_id)
        if exclude_accounts:
            placeholders = ",".join("?" * len(exclude_accounts))
            where.append(f"account_id NOT IN ({placeholders})")
            params.extend(exclude_accounts)
        sql = "SELECT * FROM external_positions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_balances(
        self,
        broker: str | None = None,
        exclude_accounts: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list = []
        if broker is not None:
            where.append("broker = ?")
            params.append(broker)
        if exclude_accounts:
            placeholders = ",".join("?" * len(exclude_accounts))
            where.append(f"account_id NOT IN ({placeholders})")
            params.extend(exclude_accounts)
        sql = "SELECT * FROM external_balances"
        if where:
            sql += " WHERE " + " AND ".join(where)
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_total_exposure_by_symbol(
        self,
        exclude_accounts: list[str] | None = None,
    ) -> dict[str, Decimal]:
        where: list[str] = []
        params: list = []
        if exclude_accounts:
            placeholders = ",".join("?" * len(exclude_accounts))
            where.append(f"account_id NOT IN ({placeholders})")
            params.extend(exclude_accounts)
        sql = "SELECT symbol, SUM(CAST(quantity AS REAL)) FROM external_positions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY symbol"
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        return {row[0]: Decimal(str(row[1])) for row in rows}

    async def get_import_age(self, broker: str) -> float | None:
        async with self._db.execute(
            "SELECT MAX(imported_at) FROM external_balances WHERE broker = ?",
            (broker,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None or row[0] is None:
            return None
        last = datetime.fromisoformat(row[0])
        now = datetime.now(timezone.utc)
        return (now - last).total_seconds() / 3600
