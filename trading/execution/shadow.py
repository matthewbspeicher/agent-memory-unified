"""Shadow execution recording and resolution services."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4

from agents.models import ActionLevel, Opportunity
from broker.models import Bar, OrderSide, Quote
from storage.shadow import ShadowExecutionStore


class ShadowDecisionStatus(str, Enum):
    ALLOWED = "allowed"
    BLOCKED_RISK = "blocked_risk"
    BLOCKED_REGIME = "blocked_regime"
    BLOCKED_HEALTH = "blocked_health"
    BLOCKED_BROKER_UNAVAILABLE = "blocked_broker_unavailable"
    BLOCKED_ACCOUNT_UNAVAILABLE = "blocked_account_unavailable"
    BLOCKED_INVALID_QUANTITY = "blocked_invalid_quantity"
    BLOCKED_PRECONDITION = "blocked_precondition"
    BLOCKED_QUOTE_MISSING = "blocked_quote_missing"
    BLOCKED_BALANCE_MISSING = "blocked_balance_missing"
    BLOCKED_CALIBRATION = "blocked_calibration"


class ShadowResolutionStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    INSUFFICIENT_DATA = "insufficient_data"
    EXPIRED = "expired"


class ShadowExecutionRecord(dict[str, Any]):
    """Typed alias for persisted shadow execution rows."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.replace(tzinfo=None)


def _decimal_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _to_float_bps(numerator: Decimal, denominator: Decimal) -> float | None:
    if denominator <= 0:
        return None
    return float((numerator / denominator) * Decimal("10000"))


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _isoformat(value)
    if is_dataclass(value):
        return {key: _serialize_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value


class ShadowExecutor:
    def __init__(
        self,
        *,
        store: ShadowExecutionStore,
        data_bus,
        intraday_hold_period: timedelta = timedelta(minutes=60),
        fallback_hold_period: timedelta = timedelta(days=1),
    ) -> None:
        self._store = store
        self._data_bus = data_bus
        self._intraday_hold_period = intraday_hold_period
        self._fallback_hold_period = fallback_hold_period

    async def record(
        self,
        opportunity: Opportunity,
        *,
        action_level: ActionLevel,
        decision_status: ShadowDecisionStatus,
        opened_at: datetime | None = None,
        resolve_after: datetime | None = None,
        risk_snapshot: dict[str, Any] | None = None,
        sizing_snapshot: dict[str, Any] | None = None,
        regime_snapshot: dict[str, Any] | None = None,
        health_snapshot: dict[str, Any] | None = None,
    ) -> ShadowExecutionRecord:
        opened_at = opened_at or opportunity.timestamp
        resolve_after = resolve_after or self._default_resolve_after(
            opportunity, opened_at
        )

        expected_entry_price: Decimal | None = None
        expected_quantity: Decimal | None = None
        expected_notional: Decimal | None = None
        entry_price_source: str | None = None
        resolution_status = ShadowResolutionStatus.OPEN

        if decision_status == ShadowDecisionStatus.ALLOWED:
            quote = await self._data_bus.get_quote(opportunity.symbol)
            expected_entry_price, entry_price_source = self._pick_entry_price(
                side=opportunity.suggested_trade.side
                if opportunity.suggested_trade
                else None,
                quote=quote,
            )
            if expected_entry_price is None:
                decision_status = ShadowDecisionStatus.BLOCKED_QUOTE_MISSING
                resolution_status = ShadowResolutionStatus.EXPIRED
            elif opportunity.suggested_trade is not None:
                expected_quantity = opportunity.suggested_trade.quantity
                expected_notional = expected_entry_price * expected_quantity
        else:
            resolution_status = ShadowResolutionStatus.EXPIRED

        record: ShadowExecutionRecord = {
            "id": str(uuid4()),
            "opportunity_id": opportunity.id,
            "agent_name": opportunity.agent_name,
            "symbol": opportunity.symbol.ticker,
            "side": opportunity.suggested_trade.side.value
            if opportunity.suggested_trade
            else "",
            "action_level": action_level.value,
            "decision_status": decision_status.value,
            "expected_entry_price": _decimal_str(expected_entry_price),
            "expected_quantity": _decimal_str(expected_quantity),
            "expected_notional": _decimal_str(expected_notional),
            "entry_price_source": entry_price_source,
            "opportunity_snapshot": self._serialize_opportunity(opportunity),
            "risk_snapshot": risk_snapshot,
            "sizing_snapshot": sizing_snapshot,
            "regime_snapshot": regime_snapshot,
            "health_snapshot": health_snapshot,
            "opened_at": _isoformat(opened_at),
            "resolve_after": _isoformat(resolve_after),
            "resolved_at": None,
            "resolution_status": resolution_status.value,
            "resolution_price": None,
            "pnl": None,
            "return_bps": None,
            "max_favorable_bps": None,
            "max_adverse_bps": None,
            "resolution_notes": None,
        }
        await self._store.save(record)
        stored = await self._store.get(record["id"])
        return ShadowExecutionRecord(stored or record)

    def _pick_entry_price(
        self,
        *,
        side: OrderSide | None,
        quote: Quote,
    ) -> tuple[Decimal | None, str | None]:
        candidates: list[tuple[Decimal | None, str]] = []
        if side == OrderSide.BUY:
            candidates.append((quote.ask, "ask"))
        elif side == OrderSide.SELL:
            candidates.append((quote.bid, "bid"))
        candidates.append((quote.last, "last"))

        for price, source in candidates:
            if price is not None and price > 0:
                return price, source
        return None, None

    def _default_resolve_after(
        self,
        opportunity: Opportunity,
        opened_at: datetime,
    ) -> datetime:
        timeframe = str(
            opportunity.data.get("timeframe") or opportunity.data.get("window") or ""
        ).lower()
        if timeframe.endswith(("m", "h")):
            return opened_at + self._intraday_hold_period
        return opened_at + self._fallback_hold_period

    def _serialize_opportunity(self, opportunity: Opportunity) -> dict[str, Any]:
        return {
            "id": opportunity.id,
            "agent_name": opportunity.agent_name,
            "symbol": _serialize_value(opportunity.symbol),
            "signal": opportunity.signal,
            "confidence": opportunity.confidence,
            "reasoning": opportunity.reasoning,
            "data": _serialize_value(opportunity.data),
            "timestamp": _serialize_value(opportunity.timestamp),
            "status": opportunity.status.value,
            "suggested_trade": _serialize_value(opportunity.suggested_trade),
            "expires_at": _serialize_value(opportunity.expires_at),
            "broker_id": opportunity.broker_id,
            "is_exit": opportunity.is_exit,
        }


class ShadowOutcomeResolver:
    def __init__(self, *, store: ShadowExecutionStore, data_bus) -> None:
        self._store = store
        self._data_bus = data_bus

    async def resolve_due(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        now = now or _utcnow()
        records = await self._store.list_due_for_resolution(now, limit)
        resolved: list[dict[str, Any]] = []
        for record in records:
            updated = await self.resolve_record(record["id"], now=now)
            if updated is not None:
                resolved.append(updated)
        return resolved

    async def resolve_record(
        self,
        record_id: str,
        *,
        now: datetime | None = None,
    ) -> ShadowExecutionRecord | None:
        record = await self._store.get(record_id)
        if record is None:
            return None
        if record["resolution_status"] != ShadowResolutionStatus.OPEN.value:
            return ShadowExecutionRecord(record)

        symbol = record["opportunity_snapshot"]["symbol"]
        side = record["side"]
        entry_price_raw = record["expected_entry_price"]
        if not entry_price_raw:
            await self._mark_insufficient(
                record_id, now=now, reason="missing_entry_price"
            )
            updated = await self._store.get(record_id)
            return ShadowExecutionRecord(updated) if updated else None

        bars = await self._data_bus.get_historical(
            symbol=self._rehydrate_symbol(symbol),
            timeframe="1m",
            period="1d",
        )
        opened_at = datetime.fromisoformat(record["opened_at"]).replace(
            tzinfo=timezone.utc
        )
        resolve_after = datetime.fromisoformat(record["resolve_after"]).replace(
            tzinfo=timezone.utc
        )
        resolution_bar = self._resolution_bar(bars, resolve_after=resolve_after)
        if resolution_bar is None:
            await self._mark_insufficient(record_id, now=now, reason="no_bars")
            updated = await self._store.get(record_id)
            return ShadowExecutionRecord(updated) if updated else None

        eligible_bars = self._eligible_bars(
            bars,
            opened_at=opened_at,
            resolved_at=resolution_bar.timestamp,
        )
        if not eligible_bars:
            await self._mark_insufficient(record_id, now=now, reason="no_bars")
            updated = await self._store.get(record_id)
            return ShadowExecutionRecord(updated) if updated else None

        entry_price = Decimal(entry_price_raw)
        quantity = Decimal(record["expected_quantity"] or "0")
        resolution_price = resolution_bar.close
        max_high = max(bar.high for bar in eligible_bars)
        min_low = min(bar.low for bar in eligible_bars)

        if side == OrderSide.SELL.value:
            pnl = (entry_price - resolution_price) * quantity
            return_bps = _to_float_bps(entry_price - resolution_price, entry_price)
            max_favorable_bps = _to_float_bps(entry_price - min_low, entry_price)
            max_adverse_bps = _to_float_bps(entry_price - max_high, entry_price)
        else:
            pnl = (resolution_price - entry_price) * quantity
            return_bps = _to_float_bps(resolution_price - entry_price, entry_price)
            max_favorable_bps = _to_float_bps(max_high - entry_price, entry_price)
            max_adverse_bps = _to_float_bps(min_low - entry_price, entry_price)

        await self._store.mark_resolved(
            record_id,
            resolved_at=_isoformat(now or _utcnow()),
            resolution_status=ShadowResolutionStatus.RESOLVED.value,
            resolution_price=str(resolution_price),
            pnl=str(pnl.quantize(Decimal("0.01"))),
            return_bps=return_bps,
            max_favorable_bps=max_favorable_bps,
            max_adverse_bps=max_adverse_bps,
            resolution_notes={"bars_seen": len(eligible_bars)},
        )
        updated = await self._store.get(record_id)
        return ShadowExecutionRecord(updated) if updated else None

    async def _mark_insufficient(
        self,
        record_id: str,
        *,
        now: datetime | None,
        reason: str,
    ) -> None:
        await self._store.mark_resolved(
            record_id,
            resolved_at=_isoformat(now or _utcnow()),
            resolution_status=ShadowResolutionStatus.INSUFFICIENT_DATA.value,
            resolution_notes={"reason": reason},
        )

    def _eligible_bars(
        self,
        bars: list[Bar],
        *,
        opened_at: datetime,
        resolved_at: datetime,
    ) -> list[Bar]:
        eligible = [
            bar for bar in bars if opened_at <= _naive_utc(bar.timestamp) <= resolved_at
        ]
        eligible.sort(key=lambda bar: bar.timestamp)
        return eligible

    def _resolution_bar(
        self,
        bars: list[Bar],
        *,
        resolve_after: datetime,
    ) -> Bar | None:
        ordered = sorted(bars, key=lambda bar: bar.timestamp)
        for bar in ordered:
            if _naive_utc(bar.timestamp) >= resolve_after:
                return bar
        return None

    def _rehydrate_symbol(self, payload: dict[str, Any]):
        from broker.models import AssetType, OptionRight, Symbol

        return Symbol(
            ticker=payload["ticker"],
            asset_type=AssetType(payload["asset_type"]),
            exchange=payload.get("exchange"),
            currency=payload.get("currency", "USD"),
            expiry=(
                datetime.fromisoformat(payload["expiry"]).date()
                if payload.get("expiry")
                else None
            ),
            strike=(
                Decimal(payload["strike"])
                if payload.get("strike") is not None
                else None
            ),
            right=(OptionRight(payload["right"]) if payload.get("right") else None),
            multiplier=payload.get("multiplier"),
        )
