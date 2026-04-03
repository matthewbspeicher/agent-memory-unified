"""ConfidenceCalibrationStore — persists per-strategy confidence bucket summaries."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiosqlite


class ConfidenceCalibrationStore:
    """Persists strategy_confidence_calibration rows (one per agent/bucket/window)."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(
        self,
        *,
        agent_name: str,
        confidence_bucket: str,
        window_label: str,
        **fields: Any,
    ) -> None:
        """INSERT OR REPLACE a calibration summary row keyed by (agent_name, confidence_bucket, window_label)."""
        fields["agent_name"] = agent_name
        fields["confidence_bucket"] = confidence_bucket
        fields["window_label"] = window_label
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        if "created_at" not in fields:
            fields["created_at"] = fields["updated_at"]

        columns = list(fields.keys())
        placeholders = ", ".join("?" for _ in columns)
        col_names = ", ".join(columns)

        await self._db.execute(
            f"INSERT OR REPLACE INTO strategy_confidence_calibration ({col_names}) VALUES ({placeholders})",
            tuple(fields[c] for c in columns),
        )
        await self._db.commit()

    async def get(
        self,
        agent_name: str,
        confidence_bucket: str,
        window_label: str,
    ) -> dict[str, Any] | None:
        """Single row by composite PK."""
        cursor = await self._db.execute(
            """
            SELECT * FROM strategy_confidence_calibration
            WHERE agent_name = ? AND confidence_bucket = ? AND window_label = ?
            """,
            (agent_name, confidence_bucket, window_label),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_by_strategy(
        self,
        agent_name: str,
        *,
        window_label: str | None = None,
    ) -> list[dict[str, Any]]:
        """All bucket rows for a single strategy, optionally filtered by window."""
        query = "SELECT * FROM strategy_confidence_calibration WHERE agent_name = ?"
        params: list[Any] = [agent_name]

        if window_label is not None:
            query += " AND window_label = ?"
            params.append(window_label)

        query += " ORDER BY confidence_bucket ASC, window_label ASC"

        cursor = await self._db.execute(query, params)
        return [dict(row) for row in await cursor.fetchall()]

    async def list_all(
        self,
        *,
        window_label: str | None = None,
    ) -> list[dict[str, Any]]:
        """All rows, optionally filtered by window."""
        query = "SELECT * FROM strategy_confidence_calibration WHERE 1=1"
        params: list[Any] = []

        if window_label is not None:
            query += " AND window_label = ?"
            params.append(window_label)

        query += " ORDER BY agent_name ASC, confidence_bucket ASC"

        cursor = await self._db.execute(query, params)
        return [dict(row) for row in await cursor.fetchall()]

    async def get_distinct_strategies(self) -> list[str]:
        """SELECT DISTINCT agent_name."""
        cursor = await self._db.execute(
            "SELECT DISTINCT agent_name FROM strategy_confidence_calibration ORDER BY agent_name"
        )
        rows = await cursor.fetchall()
        return [row["agent_name"] for row in rows]

    async def delete_by_strategy(self, agent_name: str, *, window_label: str | None = None) -> None:
        """Delete rows for a strategy (optionally by window) to support recalculation."""
        if window_label is not None:
            await self._db.execute(
                "DELETE FROM strategy_confidence_calibration WHERE agent_name = ? AND window_label = ?",
                (agent_name, window_label),
            )
        else:
            await self._db.execute(
                "DELETE FROM strategy_confidence_calibration WHERE agent_name = ?",
                (agent_name,),
            )
        await self._db.commit()
