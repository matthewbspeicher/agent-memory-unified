"""ShadowExecutionStore persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

import aiosqlite

from storage.encoding import decode_json_column, encode_json


_JSON_COLUMNS = {
    "opportunity_snapshot",
    "risk_snapshot",
    "sizing_snapshot",
    "regime_snapshot",
    "health_snapshot",
    "resolution_notes",
}

_SHADOW_EXECUTION_COLUMNS = (
    "id",
    "opportunity_id",
    "agent_name",
    "symbol",
    "side",
    "action_level",
    "decision_status",
    "expected_entry_price",
    "expected_quantity",
    "expected_notional",
    "entry_price_source",
    "opportunity_snapshot",
    "risk_snapshot",
    "sizing_snapshot",
    "regime_snapshot",
    "health_snapshot",
    "opened_at",
    "resolve_after",
    "resolved_at",
    "resolution_status",
    "resolution_price",
    "pnl",
    "return_bps",
    "max_favorable_bps",
    "max_adverse_bps",
    "resolution_notes",
)


class ShadowExecutionStore:
    """Persistence layer for shadow_executions."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def save(self, record: dict[str, Any]) -> None:
        missing = [
            column for column in _SHADOW_EXECUTION_COLUMNS if column not in record
        ]
        if missing:
            raise ValueError(f"Missing required shadow execution fields: {missing}")

        fields = [
            encode_json(record[column]) if column in _JSON_COLUMNS else record[column]
            for column in _SHADOW_EXECUTION_COLUMNS
        ]
        placeholders = ", ".join("?" for _ in _SHADOW_EXECUTION_COLUMNS)
        assignments = ", ".join(
            f"{column} = excluded.{column}"
            for column in _SHADOW_EXECUTION_COLUMNS
            if column != "id"
        )
        await self._db.execute(
            f"""
            INSERT INTO shadow_executions ({", ".join(_SHADOW_EXECUTION_COLUMNS)})
            VALUES ({placeholders})
            ON CONFLICT(id) DO UPDATE SET
                {assignments}
            """,
            tuple(fields),
        )
        await self._db.commit()

    async def get(self, record_id: str) -> dict[str, Any] | None:
        cursor = await self._db.execute(
            "SELECT * FROM shadow_executions WHERE id = ?",
            (record_id,),
        )
        row = await cursor.fetchone()
        return self._decode_row(row) if row else None

    async def list(
        self,
        *,
        agent_name: str | None = None,
        symbol: str | None = None,
        resolution_status: str | None = None,
        decision_status: str | None = None,
        limit: int = 100,
    ) -> List[dict[str, Any]]:
        query = "SELECT * FROM shadow_executions WHERE 1=1"
        params: List[Any] = []

        if agent_name is not None:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)
        if resolution_status is not None:
            query += " AND resolution_status = ?"
            params.append(resolution_status)
        if decision_status is not None:
            query += " AND decision_status = ?"
            params.append(decision_status)

        query += " ORDER BY opened_at DESC LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [self._decode_row(row) for row in rows]

    async def list_due_for_resolution(
        self, now: str | datetime, limit: int
    ) -> List[dict[str, Any]]:
        # Production (Postgres) declares resolve_after as TIMESTAMP — asyncpg
        # rejects string parameters for datetime columns. The SQLite test DDL
        # uses TEXT, which accepts both. Pass datetime for Postgres, ISO string
        # for aiosqlite so both backends work without driver-level adapters.
        #
        # For Postgres: cast resolve_after to TIMESTAMPTZ so UTC-aware `now`
        # can be compared against it. For aiosqlite (TEXT column): use ISO string.
        if self._is_postgres():
            cutoff = self._coerce_datetime_param(now)
            query = """
                SELECT *
                FROM shadow_executions
                WHERE resolution_status = 'open'
                  AND resolve_after::timestamptz <= ?
                ORDER BY resolve_after ASC
                LIMIT ?
            """
            cursor = await self._db.execute(query, (cutoff, limit))
        else:
            cutoff = self._coerce_datetime_param(now)
            cursor = await self._db.execute(
                """
                SELECT *
                FROM shadow_executions
                WHERE resolution_status = 'open'
                  AND resolve_after <= ?
                ORDER BY resolve_after ASC
                LIMIT ?
                """,
                (cutoff, limit),
            )
        rows = await cursor.fetchall()
        return [self._decode_row(row) for row in rows]

    def _coerce_datetime_param(self, value: str | datetime) -> str | datetime:
        """Return the right parameter shape for the current db driver.

        PostgresDB (asyncpg) needs a timezone-aware datetime for TIMESTAMP columns.
        aiosqlite needs an ISO string for TEXT columns.
        """
        if isinstance(value, str):
            # Incoming string — convert to datetime when the driver is asyncpg
            if self._is_postgres():
                try:
                    dt = datetime.fromisoformat(value)
                except ValueError:
                    return value
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            return value
        # datetime input — normalize to UTC-aware
        dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt if self._is_postgres() else dt.isoformat()

    def _is_postgres(self) -> bool:
        return hasattr(self._db, "_pool")

    async def mark_resolved(
        self,
        record_id: str,
        *,
        resolved_at: str,
        resolution_status: str,
        resolution_price: str | None = None,
        pnl: str | None = None,
        return_bps: float | None = None,
        max_favorable_bps: float | None = None,
        max_adverse_bps: float | None = None,
        resolution_notes: Any = None,
    ) -> None:
        await self._db.execute(
            """
            UPDATE shadow_executions
            SET resolved_at = ?,
                resolution_status = ?,
                resolution_price = ?,
                pnl = ?,
                return_bps = ?,
                max_favorable_bps = ?,
                max_adverse_bps = ?,
                resolution_notes = ?
            WHERE id = ?
            """,
            (
                resolved_at,
                resolution_status,
                resolution_price,
                pnl,
                return_bps,
                max_favorable_bps,
                max_adverse_bps,
                encode_json(resolution_notes),
                record_id,
            ),
        )
        await self._db.commit()

    async def summary_by_agent(self) -> List[dict[str, Any]]:
        cursor = await self._db.execute(
            """
            SELECT
                agent_name,
                COUNT(*) AS total_count,
                SUM(CASE WHEN resolution_status = 'open' THEN 1 ELSE 0 END) AS pending_count,
                SUM(CASE WHEN resolved_at IS NOT NULL THEN 1 ELSE 0 END) AS resolved_count,
                COALESCE(SUM(CAST(pnl AS REAL)), 0) AS total_pnl,
                AVG(return_bps) AS avg_return_bps
            FROM shadow_executions
            GROUP BY agent_name
            ORDER BY agent_name ASC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def summary_for_agent(self, agent_name: str) -> dict[str, Any] | None:
        """Get summary stats for a specific agent."""
        cursor = await self._db.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                SUM(CASE WHEN decision_status = 'allowed' THEN 1 ELSE 0 END) AS allowed_count,
                SUM(CASE WHEN decision_status != 'allowed' THEN 1 ELSE 0 END) AS blocked_count,
                SUM(CASE WHEN resolution_status = 'resolved' THEN 1 ELSE 0 END) AS resolved_count,
                SUM(CASE WHEN resolution_status = 'open' THEN 1 ELSE 0 END) AS pending_count,
                COALESCE(AVG(CAST(pnl AS REAL)), 0) AS avg_pnl,
                COALESCE(SUM(CAST(pnl AS REAL)), 0) AS total_pnl,
                AVG(return_bps) AS avg_return_bps,
                AVG(max_favorable_bps) AS avg_favorable_bps,
                AVG(max_adverse_bps) AS avg_adverse_bps
            FROM shadow_executions
            WHERE agent_name = ?
            """,
            (agent_name,),
        )
        row = await cursor.fetchone()
        if row is None or row[0] == 0:
            return None

        data = dict(row)

        # Calculate win rate and Sharpe ratio from resolved trades
        if data["resolved_count"] > 0:
            # Win rate
            win_cursor = await self._db.execute(
                """
                SELECT COUNT(*) FROM shadow_executions
                WHERE agent_name = ? AND resolution_status = 'resolved'
                AND CAST(pnl AS REAL) > 0
                """,
                (agent_name,),
            )
            win_row = await win_cursor.fetchone()
            data["win_rate"] = (win_row[0] / data["resolved_count"]) if win_row else 0.0

            # Sharpe Ratio (annualized pseudo-sharpe)
            # Fetch all resolved returns
            ret_cursor = await self._db.execute(
                "SELECT return_bps FROM shadow_executions WHERE agent_name = ? AND resolution_status = 'resolved'",
                (agent_name,),
            )
            returns = [r[0] for r in await ret_cursor.fetchall() if r[0] is not None]
            if len(returns) > 1:
                import statistics

                avg_ret = statistics.mean(returns)
                stdev = statistics.stdev(returns)
                if stdev > 0:
                    # Daily Sharpe * sqrt(252) — assume roughly daily resolution for simplicity
                    # or just return the raw ratio if timeframe varies.
                    # Standardizing on raw ratio per trade for now as a "Quality Score"
                    data["sharpe_ratio"] = avg_ret / stdev
                else:
                    data["sharpe_ratio"] = 0.0
            else:
                data["sharpe_ratio"] = 0.0
        else:
            data["win_rate"] = 0.0
            data["sharpe_ratio"] = 0.0

        return data

    def _decode_row(self, row: aiosqlite.Row) -> dict[str, Any]:
        data = dict(row)
        for column in _JSON_COLUMNS:
            data[column] = decode_json_column(data.get(column))
        return data
