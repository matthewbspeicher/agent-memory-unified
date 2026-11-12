from __future__ import annotations
import dataclasses
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import aiosqlite

from agents.models import Opportunity, OpportunityStatus
from broker.models import AssetType, Symbol
from broker.order_terms import ORDER_TYPES, decode_order, encode_order

# Key in the stored data payload holding the exact Order terms, so an approved
# Opportunity can be turned back into the order its Agent proposed.
ORDER_TERMS_KEY = "order_terms"


class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        import datetime
        from enum import Enum

        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


def _serialize_suggested_trade(opp: Opportunity) -> str:
    if opp.suggested_trade is None:
        return json.dumps(None)
    d = dataclasses.asdict(opp.suggested_trade)
    d["symbol"] = opp.suggested_trade.symbol.ticker
    d["side"] = opp.suggested_trade.side.value
    d["quantity"] = str(opp.suggested_trade.quantity)
    return json.dumps(d, cls=_DecimalEncoder)


def _utc(value) -> datetime:
    stamp = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


class OpportunityStore:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def save(self, opp: Opportunity) -> None:
        payload = dict(opp.data)
        payload.setdefault("asset_type", opp.symbol.asset_type.value)
        if opp.broker_id is not None:
            payload.setdefault("broker_id", opp.broker_id)
        if type(opp.suggested_trade) in ORDER_TYPES.values():
            payload[ORDER_TERMS_KEY] = encode_order(opp.suggested_trade)
        await self._db.execute(
            """INSERT OR REPLACE INTO opportunities
               (id, agent_name, symbol, signal, confidence, reasoning, suggested_trade, status, expires_at, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                opp.id,
                opp.agent_name,
                opp.symbol.ticker,
                opp.signal,
                opp.confidence,
                opp.reasoning,
                _serialize_suggested_trade(opp),
                opp.status.value,
                opp.expires_at.isoformat() if opp.expires_at else None,
                json.dumps(payload, cls=_DecimalEncoder),
            ),
        )
        await self._db.commit()

    async def get(self, opportunity_id: str) -> dict[str, Any] | None:
        cursor = await self._db.execute(
            "SELECT * FROM opportunities WHERE id = ?",
            (opportunity_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def list(
        self,
        agent_name: str | None = None,
        symbol: str | None = None,
        signal: str | None = None,
        status: str | None = None,
        limit: int = 50,
        min_age_hours: int | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM opportunities WHERE 1=1"
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
        if status:
            query += " AND status = ?"
            params.append(status)
        if min_age_hours is not None:
            query += f" AND created_at <= datetime('now', '-{min_age_hours} hours')"
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor = await self._db.execute(query, params)
        return [dict(row) for row in await cursor.fetchall()]

    async def update_status(
        self, opportunity_id: str, status: OpportunityStatus
    ) -> None:
        await self._db.execute(
            "UPDATE opportunities SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status.value, opportunity_id),
        )
        await self._db.commit()

    async def transition(
        self,
        opportunity_id: str,
        expected: OpportunityStatus,
        to: OpportunityStatus,
    ) -> bool:
        """Change status only if it is still `expected`; True if this call changed it."""
        async with self._db.execute(
            "UPDATE opportunities SET status = ?, updated_at = datetime('now') "
            "WHERE id = ? AND status = ? RETURNING id",
            (to.value, opportunity_id, expected.value),
        ) as cursor:
            changed = await cursor.fetchone() is not None
        await self._db.commit()
        return changed

    async def load(self, opportunity_id: str) -> Opportunity | None:
        """The stored Opportunity with its exact suggested trade.

        suggested_trade is None when no Order terms were stored: the Opportunity
        proposed no trade, or was saved before Order terms were kept.
        """
        row = await self.get(opportunity_id)
        if row is None:
            return None
        data = row["data"]
        data = json.loads(data) if isinstance(data, str) else dict(data or {})
        terms = data.get(ORDER_TERMS_KEY)
        trade = decode_order(terms) if terms else None
        symbol = (
            trade.symbol
            if trade is not None
            else Symbol(
                row["symbol"], AssetType(data.get("asset_type", AssetType.STOCK.value))
            )
        )
        return Opportunity(
            id=row["id"],
            agent_name=row["agent_name"],
            symbol=symbol,
            signal=row["signal"],
            confidence=row["confidence"],
            reasoning=row["reasoning"],
            data=data,
            timestamp=_utc(row["created_at"]),
            status=OpportunityStatus(row["status"]),
            suggested_trade=trade,
            expires_at=_utc(row["expires_at"]) if row["expires_at"] else None,
            broker_id=data.get("broker_id"),
        )

    async def update_data(self, opportunity_id: str, data: dict[str, Any]) -> None:
        await self._db.execute(
            "UPDATE opportunities SET data = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(data, cls=_DecimalEncoder), opportunity_id),
        )
        await self._db.commit()

    async def save_snapshot(
        self, opportunity_id: str, snapshot: dict[str, Any]
    ) -> None:
        await self._db.execute(
            """INSERT OR REPLACE INTO opportunity_snapshots (opportunity_id, snapshot_data)
               VALUES (?, ?)""",
            (opportunity_id, json.dumps(snapshot, cls=_DecimalEncoder)),
        )
        await self._db.commit()

    async def get_snapshot(self, opportunity_id: str) -> dict[str, Any] | None:
        cursor = await self._db.execute(
            "SELECT snapshot_data FROM opportunity_snapshots WHERE opportunity_id = ?",
            (opportunity_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return json.loads(row["snapshot_data"])
