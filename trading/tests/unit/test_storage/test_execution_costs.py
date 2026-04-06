"""Unit tests for ExecutionCostStore."""

from __future__ import annotations

import aiosqlite
import pytest

from storage.db import init_db
from storage.execution_costs import ExecutionCostStore


@pytest.fixture
async def store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield ExecutionCostStore(db)
    await db.close()


def _event(order_id: str = "ord-001", **overrides) -> dict:
    defaults = {
        "opportunity_id": "opp-001",
        "agent_name": "rsi_agent",
        "symbol": "AAPL",
        "broker_id": "ib",
        "account_id": "U123",
        "side": "BUY",
        "order_type": "market",
        "decision_time": "2026-03-25T10:00:00",
        "decision_bid": "149.50",
        "decision_ask": "150.50",
        "decision_last": "150.00",
        "decision_price": "150.00",
        "fill_time": "2026-03-25T10:00:01",
        "fill_price": "150.25",
        "filled_quantity": "10",
        "fees_total": "1.00",
        "spread_bps": "66.67",
        "slippage_bps": 16.67,
        "notional": "1500.00",
        "status": "filled",
        "fill_source": "immediate",
    }
    defaults.update(overrides)
    return defaults


class TestExecutionCostStore:
    async def test_insert_and_list(self, store: ExecutionCostStore):
        await store.insert(order_id="ord-001", **_event("ord-001"))
        rows = await store.list_events()
        assert len(rows) == 1
        assert rows[0]["order_id"] == "ord-001"
        assert rows[0]["symbol"] == "AAPL"

    async def test_insert_multiple(self, store: ExecutionCostStore):
        await store.insert(order_id="ord-001", **_event("ord-001", symbol="AAPL"))
        await store.insert(order_id="ord-002", **_event("ord-002", symbol="TSLA"))
        rows = await store.list_events()
        assert len(rows) == 2

    async def test_filter_by_symbol(self, store: ExecutionCostStore):
        await store.insert(order_id="ord-001", **_event("ord-001", symbol="AAPL"))
        await store.insert(order_id="ord-002", **_event("ord-002", symbol="TSLA"))
        rows = await store.list_events(symbol="AAPL")
        assert len(rows) == 1
        assert rows[0]["symbol"] == "AAPL"

    async def test_filter_by_broker_id(self, store: ExecutionCostStore):
        await store.insert(order_id="ord-001", **_event("ord-001", broker_id="ib"))
        await store.insert(order_id="ord-002", **_event("ord-002", broker_id="alpaca"))
        rows = await store.list_events(broker_id="ib")
        assert len(rows) == 1
        assert rows[0]["broker_id"] == "ib"

    async def test_filter_by_agent_name(self, store: ExecutionCostStore):
        await store.insert(
            order_id="ord-001", **_event("ord-001", agent_name="rsi_agent")
        )
        await store.insert(
            order_id="ord-002", **_event("ord-002", agent_name="macd_agent")
        )
        rows = await store.list_events(agent_name="rsi_agent")
        assert len(rows) == 1
        assert rows[0]["agent_name"] == "rsi_agent"

    async def test_filter_by_order_type(self, store: ExecutionCostStore):
        await store.insert(order_id="ord-001", **_event("ord-001", order_type="market"))
        await store.insert(order_id="ord-002", **_event("ord-002", order_type="limit"))
        rows = await store.list_events(order_type="market")
        assert len(rows) == 1
        assert rows[0]["order_type"] == "market"

    async def test_filter_by_window_start(self, store: ExecutionCostStore):
        await store.insert(
            order_id="ord-001",
            **_event("ord-001", decision_time="2026-03-20T10:00:00"),
        )
        await store.insert(
            order_id="ord-002",
            **_event("ord-002", decision_time="2026-03-25T10:00:00"),
        )
        rows = await store.list_events(window_start="2026-03-24T00:00:00")
        assert len(rows) == 1
        assert rows[0]["order_id"] == "ord-002"

    async def test_get_grouped_summary_by_symbol(self, store: ExecutionCostStore):
        await store.insert(
            order_id="ord-001",
            **_event("ord-001", symbol="AAPL", slippage_bps=10.0),
        )
        await store.insert(
            order_id="ord-002",
            **_event("ord-002", symbol="AAPL", slippage_bps=20.0),
        )
        await store.insert(
            order_id="ord-003",
            **_event("ord-003", symbol="TSLA", slippage_bps=5.0),
        )
        summary = await store.get_grouped_summary("symbol")
        assert len(summary) == 2
        aapl = next(r for r in summary if r["group_key"] == "AAPL")
        assert aapl["trade_count"] == 2
        assert aapl["avg_slippage_bps"] == pytest.approx(15.0)

    async def test_get_worst_groups(self, store: ExecutionCostStore):
        await store.insert(
            order_id="ord-001",
            **_event("ord-001", symbol="AAPL", slippage_bps=50.0),
        )
        await store.insert(
            order_id="ord-002",
            **_event("ord-002", symbol="TSLA", slippage_bps=10.0),
        )
        await store.insert(
            order_id="ord-003",
            **_event("ord-003", symbol="MSFT", slippage_bps=30.0),
        )
        worst = await store.get_worst_groups("symbol", limit=2)
        assert len(worst) == 2
        assert worst[0]["group_key"] == "AAPL"
        assert worst[1]["group_key"] == "MSFT"

    async def test_null_bid_ask_stored(self, store: ExecutionCostStore):
        ev = _event("ord-null")
        ev["decision_bid"] = None
        ev["decision_ask"] = None
        ev["spread_bps"] = None
        await store.insert(order_id="ord-null", **ev)
        rows = await store.list_events()
        assert rows[0]["spread_bps"] is None

    async def test_empty_list_returns_empty(self, store: ExecutionCostStore):
        rows = await store.list_events()
        assert rows == []

    async def test_grouped_summary_invalid_group_raises(
        self, store: ExecutionCostStore
    ):
        with pytest.raises(ValueError):
            await store.get_grouped_summary("invalid_column")
