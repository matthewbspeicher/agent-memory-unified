"""SignalFeatureStore — persists signal-time feature rows keyed by opportunity_id."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite


class SignalFeatureStore:
    """Persists signal_features rows (one per routed opportunity).

    Canonical ownership:
    - opportunities: intent and status
    - opportunity_snapshots: legacy/debug quote snapshot
    - signal_features: research-grade signal-time context (this table)
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(self, opportunity_id: str, **fields: Any) -> None:
        """INSERT OR REPLACE a signal_features row keyed by opportunity_id.

        Idempotent: repeated calls for the same opportunity_id update the row.
        The feature_payload field is JSON-serialised automatically if a dict is passed.
        """
        # Force opportunity_id to be first so PostgresDB adapter ON CONFLICT works correctly
        ordered_fields = {"opportunity_id": opportunity_id}
        ordered_fields.update(fields)
        ordered_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        if "created_at" not in ordered_fields:
            ordered_fields["created_at"] = ordered_fields["updated_at"]

        # Ensure feature_payload is stored as JSON string
        if "feature_payload" in ordered_fields and isinstance(ordered_fields["feature_payload"], dict):
            ordered_fields["feature_payload"] = json.dumps(ordered_fields["feature_payload"])
        elif "feature_payload" not in ordered_fields:
            ordered_fields["feature_payload"] = "{}"

        columns = list(ordered_fields.keys())
        placeholders = ", ".join("?" for _ in columns)
        col_names = ", ".join(columns)
        
        # Build ON CONFLICT DO UPDATE clause
        update_set = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "opportunity_id")

        await self._db.execute(
            f"INSERT INTO signal_features ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT(opportunity_id) DO UPDATE SET {update_set}",
            tuple(ordered_fields[c] for c in columns),
        )
        await self._db.commit()

    async def get(self, opportunity_id: str) -> dict[str, Any] | None:
        """Single row by opportunity_id. Returns None if not found."""
        cursor = await self._db.execute(
            "SELECT * FROM signal_features WHERE opportunity_id = ?",
            (opportunity_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        _decode_payload(result)
        return result

    async def list_by_agent(
        self,
        agent_name: str,
        *,
        limit: int = 100,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filter by agent_name, optionally in a time window."""
        query = "SELECT * FROM signal_features WHERE agent_name = ?"
        params: list[Any] = [agent_name]
        if start:
            query += " AND opportunity_timestamp >= ?"
            params.append(start)
        if end:
            query += " AND opportunity_timestamp <= ?"
            params.append(end)
        query += " ORDER BY opportunity_timestamp DESC LIMIT ?"
        params.append(limit)
        cursor = await self._db.execute(query, params)
        rows = [dict(r) for r in await cursor.fetchall()]
        for r in rows:
            _decode_payload(r)
        return rows

    async def list_by_symbol(
        self,
        symbol: str,
        agent_name: str | None = None,
        *,
        limit: int = 100,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filter by symbol, optionally further by agent and time window."""
        query = "SELECT * FROM signal_features WHERE symbol = ?"
        params: list[Any] = [symbol]
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if start:
            query += " AND opportunity_timestamp >= ?"
            params.append(start)
        if end:
            query += " AND opportunity_timestamp <= ?"
            params.append(end)
        query += " ORDER BY opportunity_timestamp DESC LIMIT ?"
        params.append(limit)
        cursor = await self._db.execute(query, params)
        rows = [dict(r) for r in await cursor.fetchall()]
        for r in rows:
            _decode_payload(r)
        return rows

    async def list_filtered(
        self,
        agent_name: str | None = None,
        symbol: str | None = None,
        signal: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """General-purpose filtered list. All filters are optional."""
        query = "SELECT * FROM signal_features WHERE 1=1"
        params: list[Any] = []
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if signal:
            query += " AND signal = ?"
            params.append(signal)
        if start:
            query += " AND opportunity_timestamp >= ?"
            params.append(start)
        if end:
            query += " AND opportunity_timestamp <= ?"
            params.append(end)
        query += " ORDER BY opportunity_timestamp DESC LIMIT ?"
        params.append(limit)
        cursor = await self._db.execute(query, params)
        rows = [dict(r) for r in await cursor.fetchall()]
        for r in rows:
            _decode_payload(r)
        return rows

    async def get_join_for_opportunity(self, opportunity_id: str) -> dict[str, Any] | None:
        """Join signal_features with opportunities for attribution research.

        Returns a merged dict of both tables for the given opportunity_id.
        This is the canonical join path for walk-forward optimization and attribution.
        signal_features.opportunity_id -> opportunities.id
        """
        cursor = await self._db.execute(
            """
            SELECT sf.*, o.status AS opp_status, o.reasoning, o.suggested_trade
            FROM signal_features sf
            JOIN opportunities o ON sf.opportunity_id = o.id
            WHERE sf.opportunity_id = ?
            """,
            (opportunity_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        _decode_payload(result)
        return result


def _decode_payload(row: dict[str, Any]) -> None:
    """Decode feature_payload JSON string to dict in-place."""
    payload = row.get("feature_payload")
    if isinstance(payload, str):
        try:
            row["feature_payload"] = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            row["feature_payload"] = {}
