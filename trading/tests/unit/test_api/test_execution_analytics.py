"""Tests for execution analytics API routes."""

from __future__ import annotations

import os

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from config import Config
from storage.db import init_db
from storage.execution_costs import ExecutionCostStore


@pytest.fixture
def _env():
    os.environ["STA_API_KEY"] = "test-key"
    from api.auth import _get_settings

    _get_settings.cache_clear()
    yield
    _get_settings.cache_clear()


def _event(order_id: str, **overrides) -> dict:
    defaults = {
        "opportunity_id": f"opp-{order_id}",
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
        "spread_bps": 66.67,
        "slippage_bps": 16.67,
        "notional": "1500.00",
        "status": "filled",
        "fill_source": "immediate",
    }
    defaults.update(overrides)
    return defaults


@pytest.fixture
async def app_with_events(_env):
    settings = Config(broker_mode="paper", api_key="test-key")
    app = create_app(enable_agent_framework=False, config=settings)
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    app.state.db = db

    store = ExecutionCostStore(db)
    await store.insert(
        order_id="ord-001",
        **_event("ord-001", symbol="AAPL", broker_id="ib", slippage_bps=20.0),
    )
    await store.insert(
        order_id="ord-002",
        **_event("ord-002", symbol="TSLA", broker_id="ib", slippage_bps=5.0),
    )
    await store.insert(
        order_id="ord-003",
        **_event(
            "ord-003",
            symbol="AAPL",
            broker_id="alpaca",
            slippage_bps=50.0,
            agent_name="macd_agent",
        ),
    )
    await store.insert(
        order_id="ord-004",
        **_event(
            "ord-004",
            symbol="MSFT",
            broker_id="ib",
            slippage_bps=15.0,
            order_type="limit",
        ),
    )

    yield app
    await db.close()


class TestSummaryEndpoint:
    async def test_summary_returns_grouped_data(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get(
            "/analytics/execution-costs/summary?group_by=symbol",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        keys = [d["group_key"] for d in data]
        assert "AAPL" in keys

    async def test_summary_group_by_broker(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get(
            "/analytics/execution-costs/summary?group_by=broker_id",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        keys = [d["group_key"] for d in data]
        assert "ib" in keys

    async def test_summary_filter_by_broker(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get(
            "/analytics/execution-costs/summary?group_by=symbol&broker_id=alpaca",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["group_key"] == "AAPL"

    async def test_summary_requires_auth(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get("/analytics/execution-costs/summary")
        assert resp.status_code in (401, 403)

    async def test_summary_empty_db(self, _env):
        settings = Config(broker_mode="paper", api_key="test-key")
        app = create_app(enable_agent_framework=False, config=settings)
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await init_db(db)
        app.state.db = db
        client = TestClient(app)
        resp = client.get(
            "/analytics/execution-costs/summary",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        assert resp.json() == []
        await db.close()


class TestTradesEndpoint:
    async def test_trades_returns_rows(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get(
            "/analytics/execution-costs/trades",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4

    async def test_trades_filter_by_symbol(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get(
            "/analytics/execution-costs/trades?symbol=AAPL",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(r["symbol"] == "AAPL" for r in data)

    async def test_trades_filter_by_order_type(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get(
            "/analytics/execution-costs/trades?order_type=limit",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["order_type"] == "limit"

    async def test_trades_pagination(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get(
            "/analytics/execution-costs/trades?limit=2&offset=0",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        page1 = resp.json()
        assert len(page1) == 2

        resp2 = client.get(
            "/analytics/execution-costs/trades?limit=2&offset=2",
            headers={"X-API-Key": "test-key"},
        )
        page2 = resp2.json()
        assert len(page2) == 2
        # Verify pages are different
        assert page1[0]["order_id"] != page2[0]["order_id"]

    async def test_trades_requires_auth(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get("/analytics/execution-costs/trades")
        assert resp.status_code in (401, 403)


class TestWorstEndpoint:
    async def test_worst_returns_sorted_by_slippage(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get(
            "/analytics/execution-costs/worst?group_by=symbol",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        # First result should have highest avg_slippage_bps
        slippages = [
            d["avg_slippage_bps"] for d in data if d["avg_slippage_bps"] is not None
        ]
        assert slippages == sorted(slippages, reverse=True)

    async def test_worst_respects_limit(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get(
            "/analytics/execution-costs/worst?group_by=symbol&limit=2",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= 2

    async def test_worst_group_by_broker(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get(
            "/analytics/execution-costs/worst?group_by=broker_id",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    async def test_worst_requires_auth(self, app_with_events):
        client = TestClient(app_with_events)
        resp = client.get("/analytics/execution-costs/worst")
        assert resp.status_code in (401, 403)
