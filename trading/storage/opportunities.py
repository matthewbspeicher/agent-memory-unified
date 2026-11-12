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

# Keys in the stored data payload that belong to the store, not the Agent.
# An Agent's own data is stripped of them on save, so nothing an Agent (or the
# language model behind it) writes can supply the order that approval executes.
ORDER_TERMS_KEY = "order_terms"  # the exact order the Agent proposed
EXIT_KEY = "exit"  # whether it closes a position, and what fraction
APPROVABLE_KEY = "approvable"  # set once the router offers it for approval
BROKER_KEY = "broker_id"
_STORE_KEYS = (ORDER_TERMS_KEY, EXIT_KEY, APPROVABLE_KEY, BROKER_KEY)
_NUMERIC_TERMS = ("quantity", "limit_price", "stop_price", "trail_amount", "trail_percent")


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
    return json.loads(raw) if isinstance(raw, str) else dict(raw or {})


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


# How the PostgreSQL driver names the expiry argument of the save statement.
_EXPIRY_REFUSED = "query argument $9:"
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
        # True once the database has taken expiry as a datetime after refusing text.
        self._expiry_is_timestamp = False

    async def save(self, opp: Opportunity) -> bool:
        """Store a routed Opportunity; False if an acted-on one already has its id."""
        payload = {k: v for k, v in opp.data.items() if k not in _STORE_KEYS}
        payload.setdefault("asset_type", opp.symbol.asset_type.value)
        if opp.broker_id is not None:
            payload[BROKER_KEY] = opp.broker_id
        if type(opp.suggested_trade) in ORDER_TYPES.values():
            payload[ORDER_TERMS_KEY] = _exact_terms(opp.suggested_trade)
        if opp.is_exit:
            payload[EXIT_KEY] = {"fraction": opp._exit_fraction}
        as_timestamp = self._expiry_is_timestamp
        try:
            written = await self._upsert(opp, payload, as_timestamp)
        except Exception as error:
            # SQLite and a PostgreSQL TEXT column take expiry as ISO text. The
            # bootstrap script's PostgreSQL column is TIMESTAMP, for which the
            # driver accepts only a datetime. It refuses while encoding the
            # arguments, so the statement itself was never run.
            if (
                as_timestamp
                or opp.expires_at is None
                or type(error).__name__ != "DataError"
                or _EXPIRY_REFUSED not in str(error)
                or "datetime" not in str(error)
            ):
                raise
            written = await self._upsert(opp, payload, True)
            self._expiry_is_timestamp = True
        await self._db.commit()
        return written

    @staticmethod
    def _expiry(opp: Opportunity, as_timestamp: bool):
        if opp.expires_at is None:
            return None
        if as_timestamp:
            # The column has no time zone; it holds UTC, as load() reads it.
            return _utc(opp.expires_at).astimezone(timezone.utc).replace(tzinfo=None)
        return opp.expires_at.isoformat()

    async def _upsert(
        self, opp: Opportunity, payload: dict[str, Any], as_timestamp: bool
    ) -> bool:
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
                self._expiry(opp, as_timestamp),  # the ninth argument
                json.dumps(payload, cls=_DecimalEncoder),
            ),
        ) as cursor:
            return await cursor.fetchone() is not None

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

    async def mark_approvable(self, opportunity_id: str) -> None:
        """Record that the router offered this Opportunity for approval.

        The router calls this right after saving, so the row is pending, or
        was claimed in between by an approval of the Opportunity it replaced.
        That approval sees the new offer and releases its claim.
        """
        offerable = (OpportunityStatus.PENDING.value, OpportunityStatus.APPROVED.value)
        row = await self.get(opportunity_id)
        if row is None or row["status"] not in offerable:
            return
        data = _parse_data(row["data"])
        # The offer time is kept here, in UTC, because the table's own
        # timestamps depend on the database session's time zone.
        data[APPROVABLE_KEY] = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            # Only the row that was read: a save in between must not have its
            # data overwritten with the earlier Opportunity's.
            "UPDATE opportunities SET data = ? "
            "WHERE id = ? AND status IN (?, ?) AND updated_at = ?",
            (
                json.dumps(data, cls=_DecimalEncoder),
                opportunity_id,
                *offerable,
                row["updated_at"],
            ),
        )
        await self._db.commit()

    async def offered_at(self, opportunity_id: str) -> datetime | None:
        """When the router offered this Opportunity for approval, if it did."""
        row = await self.get(opportunity_id)
        offered = _parse_data(row["data"]).get(APPROVABLE_KEY) if row else None
        try:
            return _utc(offered) if isinstance(offered, str) else None
        except ValueError:
            return None

    async def is_approvable(self, opportunity_id: str) -> bool:
        return await self.offered_at(opportunity_id) is not None

    async def update_data(self, opportunity_id: str, data: dict[str, Any]) -> None:
        """Replace the Agent's data, keeping the keys the store owns."""
        row = await self.get(opportunity_id)
        kept = _parse_data(row["data"]) if row else {}
        merged = {k: v for k, v in data.items() if k not in _STORE_KEYS}
        merged.update({k: kept[k] for k in _STORE_KEYS if k in kept})
        await self._db.execute(
            "UPDATE opportunities SET data = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(merged, cls=_DecimalEncoder), opportunity_id),
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
