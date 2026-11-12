from __future__ import annotations
import dataclasses
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

import aiosqlite

from agents.models import Opportunity, OpportunityStatus
from broker.models import AssetType, Symbol
from broker.order_terms import ORDER_TYPES, decode_order, encode_order

# Keys in the stored data payload that belong to the store, not the Agent.
# An Agent's own data is stripped of them on save, so nothing an Agent (or the
# language model behind it) writes can supply the order that approval executes.
ORDER_TERMS_KEY = "order_terms"  # the exact order the Agent proposed
EXIT_KEY = "exit"  # whether it closes a position, and what fraction
APPROVABLE_KEY = "approvable"  # set once the router offers it for approval
BROKER_KEY = "broker_id"
REVISION_KEY = "_opportunity_revision"
_STORE_KEYS = (ORDER_TERMS_KEY, EXIT_KEY, APPROVABLE_KEY, BROKER_KEY, REVISION_KEY)
_NUMERIC_TERMS = (
    "quantity",
    "limit_price",
    "stop_price",
    "trail_amount",
    "trail_percent",
)


def _exact_terms(order) -> dict:
    """Order terms with numbers as exact decimals, as the live path reads them.

    Agents often build prices as floats; Decimal(0.57) is not Decimal("0.57").
    """
    terms = encode_order(order)
    for key in _NUMERIC_TERMS:
        value = terms["data"].get(key)
        if value is not None:
            terms["data"][key] = Decimal(str(value))
    return terms


def _parse_data(raw) -> dict[str, Any]:
    return dict((json.loads(raw) if isinstance(raw, str) else raw) or {})


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


_UNKNOWN_AGE = datetime(1970, 1, 1, tzinfo=timezone.utc)


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

    async def save(self, opp: Opportunity) -> bool:
        """Store a routed Opportunity; False if an acted-on one already has its id."""
        payload = {k: v for k, v in opp.data.items() if k not in _STORE_KEYS}
        # A durable save identity, independent of database clock precision.
        # Never accept an identity supplied by the Agent, even on a re-save.
        revision = uuid4().hex
        payload[REVISION_KEY] = revision
        payload.setdefault("asset_type", opp.symbol.asset_type.value)
        if opp.broker_id is not None:
            payload[BROKER_KEY] = opp.broker_id
        if type(opp.suggested_trade) in ORDER_TYPES.values():
            payload[ORDER_TERMS_KEY] = _exact_terms(opp.suggested_trade)
        if opp.is_exit:
            payload[EXIT_KEY] = {"fraction": opp._exit_fraction}
        # A routed Opportunity replaces an earlier one with the same id that
        # placed no order, and must then be offered again. It never replaces
        # one that was approved or may have an order out.
        async with self._db.execute(
            """INSERT INTO opportunities
               (id, agent_name, symbol, signal, confidence, reasoning, suggested_trade, status, expires_at, data, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
               ON CONFLICT (id) DO UPDATE SET
                   agent_name = excluded.agent_name,
                   symbol = excluded.symbol,
                   signal = excluded.signal,
                   confidence = excluded.confidence,
                   reasoning = excluded.reasoning,
                   suggested_trade = excluded.suggested_trade,
                   status = excluded.status,
                   expires_at = excluded.expires_at,
                   data = excluded.data,
                   created_at = datetime('now'),
                   updated_at = datetime('now')
               WHERE opportunities.status IN ('pending', 'rejected', 'expired')
               RETURNING id""",
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
        ) as cursor:
            written = await cursor.fetchone() is not None
        await self._db.commit()
        if written:
            opp.data[REVISION_KEY] = revision
        return written

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
        *,
        revision: str | None = None,
    ) -> bool:
        """Change status only if it is still `expected`; True if this call changed it."""
        if revision is not None:
            while True:
                row = await self._read_metadata(opportunity_id)
                if (
                    row is None
                    or row["status"] != expected.value
                    or _parse_data(row["data"]).get(REVISION_KEY) != revision
                ):
                    return False
                async with self._db.execute(
                    "UPDATE opportunities SET status = ?, updated_at = datetime('now') "
                    "WHERE id = ? AND status = ? "
                    "AND COALESCE(CAST(data AS TEXT), '') = ? RETURNING id",
                    (to.value, opportunity_id, expected.value, row["data"] or ""),
                ) as cursor:
                    changed = await cursor.fetchone() is not None
                await self._db.commit()
                if changed:
                    return True
                # A metadata writer may have won. Re-read, but never claim a
                # replacement suggestion or overwrite a different status.
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
        data = _parse_data(row["data"])
        trade = None
        try:
            if data.get(ORDER_TERMS_KEY):
                trade = decode_order(data[ORDER_TERMS_KEY])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            trade = None  # unreadable terms are not an order
        if trade is not None and trade.symbol.ticker != row["symbol"]:
            trade = None  # terms for a different instrument are not this order
        exit_ = data.get(EXIT_KEY)
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
            confidence=float(row["confidence"]),
            reasoning=row["reasoning"],
            data=data,
            # A row with no recorded time cannot be shown to be fresh.
            timestamp=_utc(row["created_at"] or row["updated_at"] or _UNKNOWN_AGE),
            status=OpportunityStatus(row["status"]),
            suggested_trade=trade,
            expires_at=_utc(row["expires_at"]) if row["expires_at"] else None,
            broker_id=data.get("broker_id"),
            is_exit=isinstance(exit_, dict),
            _exit_fraction=float(exit_.get("fraction", 1.0))
            if isinstance(exit_, dict)
            else 1.0,
        )

    async def _read_metadata(self, opportunity_id: str) -> dict | None:
        # Compare the database's own text representation, including JSONB's
        # canonical representation. No Python re-serialization in the predicate.
        async with self._db.execute(
            "SELECT id, status, CAST(data AS TEXT) AS data FROM opportunities WHERE id = ?",
            (opportunity_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row is not None else None

    async def _write_metadata(self, row: dict, data: dict) -> bool:
        """Atomically replace only the exact payload/status read by the caller."""
        async with self._db.execute(
            "UPDATE opportunities SET data = ?, updated_at = datetime('now') "
            "WHERE id = ? AND status = ? "
            "AND COALESCE(CAST(data AS TEXT), '') = ? RETURNING id",
            (
                json.dumps(data, cls=_DecimalEncoder),
                row["id"],
                row["status"],
                row["data"] or "",
            ),
        ) as cursor:
            changed = await cursor.fetchone() is not None
        await self._db.commit()
        return changed

    async def mark_approvable(
        self, opportunity_id: str, *, revision: str | None
    ) -> bool:
        """Offer the exact save that passed the router's gates; never a replacement."""
        if not revision:
            return False
        while True:
            row = await self._read_metadata(opportunity_id)
            if row is None or row["status"] != OpportunityStatus.PENDING.value:
                return False
            data = _parse_data(row["data"])
            if data.get(REVISION_KEY) != revision:
                return False
            if data.get(APPROVABLE_KEY):
                return True  # Publishing twice never extends approval freshness.
            data[APPROVABLE_KEY] = datetime.now(timezone.utc).isoformat()
            if await self._write_metadata(row, data):
                return True

    async def offer_identity(
        self, opportunity_id: str
    ) -> tuple[str | None, datetime | None]:
        """The durable revision and offer time from one database snapshot."""
        row = await self.get(opportunity_id)
        data = _parse_data(row["data"]) if row else {}
        offered = data.get(APPROVABLE_KEY)
        try:
            timestamp = _utc(offered) if isinstance(offered, str) else None
        except ValueError:
            timestamp = None
        return data.get(REVISION_KEY), timestamp

    async def offered_at(self, opportunity_id: str) -> datetime | None:
        """When the router offered this Opportunity for approval, if it did."""
        return (await self.offer_identity(opportunity_id))[1]

    async def is_approvable(self, opportunity_id: str) -> bool:
        return await self.offered_at(opportunity_id) is not None

    async def update_data(
        self, opportunity_id: str, data: dict[str, Any], *, revision: str | None = None
    ) -> bool:
        """Merge a metadata patch, preserving current store-owned control fields.

        Execution callers bind their patch to the save they processed. An
        unbound patch still cannot replace reserved keys or lose a new offer.
        """
        patch = {k: v for k, v in data.items() if k not in _STORE_KEYS}
        while True:
            row = await self._read_metadata(opportunity_id)
            if row is None:
                return False
            merged = _parse_data(row["data"])
            if revision is not None and merged.get(REVISION_KEY) != revision:
                return False
            merged.update(patch)
            if await self._write_metadata(row, merged):
                return True

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
