"""ExecutionCostStore — persistence and query layer for execution_cost_events."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class ExecutionCostStore:
    """Persists execution cost event rows and provides filtered reads."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def insert(self, *, order_id: str, **fields: Any) -> None:
        """Insert a new execution cost event row.

        `order_id` is required; all other columns are passed via **fields.
        Duplicate order_id rows are allowed (partial fills, retries).
        Use upsert_by_order() for idempotent writes.
        """
        fields["order_id"] = order_id
        if "created_at" not in fields:
            fields["created_at"] = datetime.now(timezone.utc).isoformat()

        columns = list(fields.keys())
        placeholders = ", ".join("?" for _ in columns)
        col_names = ", ".join(columns)

        await self._db.execute(
            f"INSERT INTO execution_cost_events ({col_names}) VALUES ({placeholders})",
            tuple(fields[c] for c in columns),
        )
        await self._db.commit()

    async def upsert_by_order(self, *, order_id: str, **fields: Any) -> None:
        """INSERT OR REPLACE keyed by order_id (idempotent for the same order)."""
        fields["order_id"] = order_id
        now = datetime.now(timezone.utc).isoformat()
        if "created_at" not in fields:
            fields["created_at"] = now

        columns = list(fields.keys())
        placeholders = ", ".join("?" for _ in columns)
        col_names = ", ".join(columns)

        await self._db.execute(
            f"""
            INSERT INTO execution_cost_events ({col_names})
            VALUES ({placeholders})
            ON CONFLICT(order_id) DO UPDATE SET
            {', '.join(f'{c}=excluded.{c}' for c in columns if c not in ('order_id', 'created_at'))}
            """,
            tuple(fields[c] for c in columns),
        )
        await self._db.commit()

    async def list_events(
        self,
        *,
        broker_id: str | None = None,
        symbol: str | None = None,
        agent_name: str | None = None,
        order_type: str | None = None,
        window_start: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return per-trade execution cost rows with optional filters."""
        query = "SELECT * FROM execution_cost_events WHERE 1=1"
        params: list[Any] = []

        if broker_id is not None:
            query += " AND broker_id = ?"
            params.append(broker_id)
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)
        if agent_name is not None:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if order_type is not None:
            query += " AND order_type = ?"
            params.append(order_type)
        if window_start is not None:
            query += " AND decision_time >= ?"
            params.append(window_start)

        query += " ORDER BY decision_time DESC LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(query, params)
        return [dict(row) for row in await cursor.fetchall()]

    async def get_grouped_summary(
        self,
        group_by: str,
        *,
        broker_id: str | None = None,
        symbol: str | None = None,
        agent_name: str | None = None,
        order_type: str | None = None,
        window_start: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return aggregated execution cost metrics grouped by one dimension.

        group_by must be one of: broker_id, symbol, agent_name, order_type.
        """
        _allowed = {"broker_id", "symbol", "agent_name", "order_type"}
        if group_by not in _allowed:
            raise ValueError(f"group_by must be one of {_allowed}")

        where = "WHERE 1=1"
        params: list[Any] = []

        if broker_id is not None:
            where += " AND broker_id = ?"
            params.append(broker_id)
        if symbol is not None:
            where += " AND symbol = ?"
            params.append(symbol)
        if agent_name is not None:
            where += " AND agent_name = ?"
            params.append(agent_name)
        if order_type is not None:
            where += " AND order_type = ?"
            params.append(order_type)
        if window_start is not None:
            where += " AND decision_time >= ?"
            params.append(window_start)

        query = f"""
            SELECT
                {group_by} AS group_key,
                COUNT(*) AS trade_count,
                AVG(spread_bps) AS avg_spread_bps,
                AVG(slippage_bps) AS avg_slippage_bps,
                AVG(CAST(fees_total AS REAL)) AS avg_fee_dollars
            FROM execution_cost_events
            {where}
            GROUP BY {group_by}
            ORDER BY avg_slippage_bps DESC NULLS LAST
        """
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_worst_groups(
        self,
        group_by: str,
        *,
        window_start: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return the worst-performing groups by average slippage."""
        _allowed = {"broker_id", "symbol", "agent_name", "order_type"}
        if group_by not in _allowed:
            raise ValueError(f"group_by must be one of {_allowed}")

        where = "WHERE slippage_bps IS NOT NULL"
        params: list[Any] = []

        if window_start is not None:
            where += " AND decision_time >= ?"
            params.append(window_start)

        params.append(limit)

        query = f"""
            SELECT
                {group_by} AS group_key,
                COUNT(*) AS trade_count,
                AVG(spread_bps) AS avg_spread_bps,
                AVG(slippage_bps) AS avg_slippage_bps,
                MAX(slippage_bps) AS max_slippage_bps,
                AVG(CAST(fees_total AS REAL)) AS avg_fee_dollars
            FROM execution_cost_events
            {where}
            GROUP BY {group_by}
            ORDER BY avg_slippage_bps DESC
            LIMIT ?
        """
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
