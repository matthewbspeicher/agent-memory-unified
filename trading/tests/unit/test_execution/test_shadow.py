from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import aiosqlite
import pytest

from agents.models import ActionLevel, Opportunity
from broker.models import AssetType, Bar, MarketOrder, OrderSide, Quote, Symbol
from execution.shadow import (
    ShadowDecisionStatus,
    ShadowExecutor,
    ShadowOutcomeResolver,
)
from storage.db import init_db
from storage.shadow import ShadowExecutionStore


@pytest.fixture
async def store() -> ShadowExecutionStore:
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield ShadowExecutionStore(db)
    await db.close()


@dataclass
class StubDataBus:
    quote: Quote | None = None
    bars: list[Bar] | None = None

    async def get_quote(self, symbol: Symbol) -> Quote:
        if self.quote is None:
            raise RuntimeError("quote not configured")
        return self.quote

    async def get_historical(
        self,
        symbol: Symbol,
        timeframe: str = "1m",
        period: str = "1d",
    ) -> list[Bar]:
        return list(self.bars or [])


def _symbol(ticker: str = "AAPL") -> Symbol:
    return Symbol(ticker=ticker, asset_type=AssetType.STOCK)


def _opportunity(
    *,
    side: OrderSide = OrderSide.BUY,
    quantity: str = "10",
    ticker: str = "AAPL",
) -> Opportunity:
    symbol = _symbol(ticker)
    return Opportunity(
        id=f"opp-{ticker.lower()}",
        agent_name="rsi_agent",
        symbol=symbol,
        signal="momentum",
        confidence=0.82,
        reasoning="test setup",
        data={"window": "5m"},
        timestamp=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
        suggested_trade=MarketOrder(
            symbol=symbol,
            side=side,
            quantity=Decimal(quantity),
            account_id="paper",
        ),
    )


class TestShadowExecutor:
    async def test_allowed_shadow_decision_records_entry_price_and_quantity(
        self,
        store: ShadowExecutionStore,
    ) -> None:
        data_bus = StubDataBus(
            quote=Quote(
                symbol=_symbol(),
                bid=Decimal("100.00"),
                ask=Decimal("100.25"),
                last=Decimal("100.10"),
            )
        )
        executor = ShadowExecutor(store=store, data_bus=data_bus)

        record = await executor.record(
            _opportunity(side=OrderSide.BUY, quantity="5"),
            action_level=ActionLevel.SUGGEST_TRADE,
            decision_status=ShadowDecisionStatus.ALLOWED,
            risk_snapshot={"status": "ok"},
            sizing_snapshot={"shares": 5},
        )

        assert record["decision_status"] == "allowed"
        assert record["expected_entry_price"] == "100.25"
        assert record["expected_quantity"] == "5"
        assert record["expected_notional"] == "501.25"
        assert record["entry_price_source"] == "ask"
        assert record["resolution_status"] == "open"
        assert record["resolve_after"] == "2026-04-01T11:00:00+00:00"

        persisted = await store.get(record["id"])
        assert persisted is not None
        assert persisted["expected_entry_price"] == "100.25"
        assert persisted["expected_quantity"] == "5"

    async def test_blocked_shadow_record_persists_without_entry_fields(
        self,
        store: ShadowExecutionStore,
    ) -> None:
        executor = ShadowExecutor(store=store, data_bus=StubDataBus())

        record = await executor.record(
            _opportunity(side=OrderSide.SELL, quantity="3"),
            action_level=ActionLevel.SUGGEST_TRADE,
            decision_status=ShadowDecisionStatus.BLOCKED_RISK,
            risk_snapshot={"rule": "max_position_size"},
        )

        assert record["decision_status"] == "blocked_risk"
        assert record["expected_entry_price"] is None
        assert record["expected_quantity"] is None
        assert record["resolution_status"] == "expired"

        persisted = await store.get(record["id"])
        assert persisted is not None
        assert persisted["decision_status"] == "blocked_risk"
        assert persisted["risk_snapshot"] == {"rule": "max_position_size"}

    async def test_sell_shadow_decision_uses_bid_entry_price(
        self,
        store: ShadowExecutionStore,
    ) -> None:
        data_bus = StubDataBus(
            quote=Quote(
                symbol=_symbol(),
                bid=Decimal("99.75"),
                ask=Decimal("100.10"),
                last=Decimal("99.90"),
            )
        )
        executor = ShadowExecutor(store=store, data_bus=data_bus)

        record = await executor.record(
            _opportunity(side=OrderSide.SELL, quantity="4"),
            action_level=ActionLevel.SUGGEST_TRADE,
            decision_status=ShadowDecisionStatus.ALLOWED,
        )

        assert record["expected_entry_price"] == "99.75"
        assert record["entry_price_source"] == "bid"

    async def test_missing_quote_prices_record_blocked_quote_missing(
        self,
        store: ShadowExecutionStore,
    ) -> None:
        data_bus = StubDataBus(
            quote=Quote(symbol=_symbol(), bid=None, ask=None, last=None)
        )
        executor = ShadowExecutor(store=store, data_bus=data_bus)

        record = await executor.record(
            _opportunity(side=OrderSide.BUY, quantity="1"),
            action_level=ActionLevel.SUGGEST_TRADE,
            decision_status=ShadowDecisionStatus.ALLOWED,
        )

        assert record["decision_status"] == "blocked_quote_missing"
        assert record["expected_entry_price"] is None
        assert record["resolution_status"] == "expired"

    async def test_non_intraday_decision_defaults_to_one_day_resolution(
        self,
        store: ShadowExecutionStore,
    ) -> None:
        executor = ShadowExecutor(
            store=store,
            data_bus=StubDataBus(
                quote=Quote(
                    symbol=_symbol(),
                    ask=Decimal("100.25"),
                    bid=Decimal("100.00"),
                    last=Decimal("100.10"),
                )
            ),
        )
        opportunity = _opportunity(side=OrderSide.BUY, quantity="1")
        opportunity.data = {}

        record = await executor.record(
            opportunity,
            action_level=ActionLevel.SUGGEST_TRADE,
            decision_status=ShadowDecisionStatus.ALLOWED,
        )

        assert record["resolve_after"] == "2026-04-02T10:00:00+00:00"


class TestShadowOutcomeResolver:
    async def test_resolver_marks_success_with_return_and_excursions(
        self,
        store: ShadowExecutionStore,
    ) -> None:
        opened_at = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
        resolve_after = opened_at + timedelta(minutes=5)
        data_bus = StubDataBus(
            bars=[
                Bar(
                    symbol=_symbol(),
                    open=Decimal("100.20"),
                    high=Decimal("101.00"),
                    low=Decimal("99.80"),
                    close=Decimal("100.90"),
                    timestamp=opened_at + timedelta(minutes=1),
                ),
                Bar(
                    symbol=_symbol(),
                    open=Decimal("100.90"),
                    high=Decimal("101.50"),
                    low=Decimal("99.50"),
                    close=Decimal("101.25"),
                    timestamp=resolve_after + timedelta(minutes=1),
                ),
            ]
        )
        executor = ShadowExecutor(
            store=store,
            data_bus=StubDataBus(
                quote=Quote(
                    symbol=_symbol(),
                    ask=Decimal("100.25"),
                    bid=Decimal("100.00"),
                    last=Decimal("100.10"),
                )
            ),
        )
        resolver = ShadowOutcomeResolver(store=store, data_bus=data_bus)

        record = await executor.record(
            _opportunity(side=OrderSide.BUY, quantity="5"),
            action_level=ActionLevel.SUGGEST_TRADE,
            decision_status=ShadowDecisionStatus.ALLOWED,
            opened_at=opened_at,
            resolve_after=resolve_after,
        )

        resolved = await resolver.resolve_record(record["id"])

        assert resolved is not None
        assert resolved["resolution_status"] == "resolved"
        assert resolved["resolution_price"] == "101.25"
        assert resolved["return_bps"] == pytest.approx(99.75, abs=0.01)
        assert resolved["max_favorable_bps"] == pytest.approx(124.69, abs=0.01)
        assert resolved["max_adverse_bps"] == pytest.approx(-74.81, abs=0.01)

        persisted = await store.get(record["id"])
        assert persisted is not None
        assert persisted["resolution_price"] == "101.25"
        assert persisted["return_bps"] == pytest.approx(99.75, abs=0.01)

    async def test_resolver_marks_insufficient_data_when_no_bars_are_available(
        self,
        store: ShadowExecutionStore,
    ) -> None:
        opened_at = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
        resolve_after = opened_at + timedelta(minutes=5)
        executor = ShadowExecutor(
            store=store,
            data_bus=StubDataBus(
                quote=Quote(
                    symbol=_symbol(),
                    ask=Decimal("100.25"),
                    bid=Decimal("100.00"),
                    last=Decimal("100.10"),
                )
            ),
        )
        resolver = ShadowOutcomeResolver(store=store, data_bus=StubDataBus(bars=[]))

        record = await executor.record(
            _opportunity(side=OrderSide.BUY, quantity="2"),
            action_level=ActionLevel.SUGGEST_TRADE,
            decision_status=ShadowDecisionStatus.ALLOWED,
            opened_at=opened_at,
            resolve_after=resolve_after,
        )

        resolved = await resolver.resolve_record(record["id"])

        assert resolved is not None
        assert resolved["resolution_status"] == "insufficient_data"
        assert resolved["resolution_price"] is None
        assert resolved["return_bps"] is None
        assert resolved["max_favorable_bps"] is None
        assert resolved["max_adverse_bps"] is None

        persisted = await store.get(record["id"])
        assert persisted is not None
        assert persisted["resolution_status"] == "insufficient_data"

    async def test_resolve_due_processes_pending_records(
        self, store: ShadowExecutionStore
    ) -> None:
        opened_at = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
        resolve_after = opened_at + timedelta(minutes=5)
        executor = ShadowExecutor(
            store=store,
            data_bus=StubDataBus(
                quote=Quote(
                    symbol=_symbol(),
                    ask=Decimal("100.25"),
                    bid=Decimal("100.00"),
                    last=Decimal("100.10"),
                )
            ),
        )
        resolver = ShadowOutcomeResolver(
            store=store,
            data_bus=StubDataBus(
                bars=[
                    Bar(
                        symbol=_symbol(),
                        open=Decimal("100.20"),
                        high=Decimal("100.80"),
                        low=Decimal("99.90"),
                        close=Decimal("100.60"),
                        timestamp=resolve_after,
                    )
                ]
            ),
        )

        record = await executor.record(
            _opportunity(side=OrderSide.BUY, quantity="1"),
            action_level=ActionLevel.SUGGEST_TRADE,
            decision_status=ShadowDecisionStatus.ALLOWED,
            opened_at=opened_at,
            resolve_after=resolve_after,
        )

        resolved = await resolver.resolve_due(now=resolve_after + timedelta(minutes=1))

        assert len(resolved) == 1
        assert resolved[0]["id"] == record["id"]
        assert resolved[0]["resolution_status"] == "resolved"
