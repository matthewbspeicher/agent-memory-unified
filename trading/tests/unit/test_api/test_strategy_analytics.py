"""Tests for strategy analytics API routes."""

from __future__ import annotations

import os

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from config import Config
from storage.db import init_db
from storage.trade_analytics import TradeAnalyticsStore


@pytest.fixture
def _env():
    os.environ["STA_API_KEY"] = "test-key"
    from api.auth import _get_settings

    _get_settings.cache_clear()
    yield
    _get_settings.cache_clear()


def _make_row(
    *,
    tracked_position_id: int,
    agent_name: str = "rsi",
    symbol: str = "AAPL",
    net_pnl: str = "100",
    gross_pnl: str = "110",
    realized_outcome: str = "win",
    exit_time: str = "2026-03-25T14:00:00Z",
    exit_reason: str = "profit_target",
    **overrides: object,
) -> dict:
    return {
        "tracked_position_id": tracked_position_id,
        "opportunity_id": f"opp-{tracked_position_id}",
        "agent_name": agent_name,
        "signal": "rsi_oversold",
        "symbol": symbol,
        "side": "buy",
        "broker_id": None,
        "account_id": None,
        "entry_time": "2026-03-25T10:00:00Z",
        "exit_time": exit_time,
        "hold_minutes": 240.0,
        "entry_price": "100",
        "exit_price": "110",
        "entry_quantity": 10,
        "entry_fees": "5",
        "exit_fees": "5",
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "gross_return_pct": 0.1,
        "net_return_pct": 0.09,
        "realized_outcome": realized_outcome,
        "exit_reason": exit_reason,
        "confidence": 0.75,
        "confidence_bucket": None,
        "strategy_version": None,
        "regime_label": None,
        "trend_regime": None,
        "volatility_regime": None,
        "liquidity_regime": None,
        "execution_slippage_bps": None,
        "entry_spread_bps": None,
        "order_type": None,
        "created_at": "2026-03-25T14:00:00Z",
        "updated_at": "2026-03-25T14:00:00Z",
        **overrides,
    }


@pytest.fixture
async def app_with_trades(_env):
    settings = Config(worker_mode=False, api_key="test-key")
    app = create_app(enable_agent_framework=False, config=settings)
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    app.state.db = db

    store = TradeAnalyticsStore(db)
    # Insert trades for two strategies
    await store.upsert(
        **_make_row(
            tracked_position_id=1,
            agent_name="rsi",
            symbol="AAPL",
            net_pnl="100",
            realized_outcome="win",
            exit_time="2026-03-25T10:00:00Z",
        )
    )
    await store.upsert(
        **_make_row(
            tracked_position_id=2,
            agent_name="rsi",
            symbol="AAPL",
            net_pnl="-30",
            realized_outcome="loss",
            exit_time="2026-03-25T11:00:00Z",
        )
    )
    await store.upsert(
        **_make_row(
            tracked_position_id=3,
            agent_name="rsi",
            symbol="TSLA",
            net_pnl="50",
            realized_outcome="win",
            exit_time="2026-03-25T12:00:00Z",
        )
    )
    await store.upsert(
        **_make_row(
            tracked_position_id=4,
            agent_name="momentum",
            symbol="NVDA",
            net_pnl="200",
            realized_outcome="win",
            exit_time="2026-03-25T13:00:00Z",
        )
    )

    yield app
    await db.close()


class TestScorecardEndpoint:
    async def test_scorecard_returns_ranked_strategies(self, app_with_trades):
        client = TestClient(app_with_trades)
        resp = client.get(
            "/analytics/strategies/scorecard", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        agent_names = [s["agent_name"] for s in data]
        assert "rsi" in agent_names
        assert "momentum" in agent_names

    async def test_scorecard_empty_result(self, _env):
        settings = Config(worker_mode=False, api_key="test-key")
        app = create_app(enable_agent_framework=False, config=settings)
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await init_db(db)
        app.state.db = db

        client = TestClient(app)
        resp = client.get(
            "/analytics/strategies/scorecard", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        assert resp.json() == []
        await db.close()

    async def test_scorecard_requires_auth(self, app_with_trades):
        client = TestClient(app_with_trades)
        resp = client.get("/analytics/strategies/scorecard")
        assert resp.status_code in (401, 403)


class TestDrilldownEndpoint:
    async def test_drilldown_returns_summary_and_series(self, app_with_trades):
        client = TestClient(app_with_trades)
        resp = client.get(
            "/analytics/strategies/rsi", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["agent_name"] == "rsi"
        assert data["summary"]["trade_count"] == 3
        assert "equity_curve" in data
        assert "top_symbols" in data
        assert "exit_reasons" in data

    async def test_drilldown_empty_strategy(self, app_with_trades):
        client = TestClient(app_with_trades)
        resp = client.get(
            "/analytics/strategies/nonexistent", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["trade_count"] == 0


class TestTradesEndpoint:
    async def test_trades_returns_paginated(self, app_with_trades):
        client = TestClient(app_with_trades)
        resp = client.get(
            "/analytics/strategies/rsi/trades?limit=2",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


class TestSymbolsEndpoint:
    async def test_symbols_returns_breakdown(self, app_with_trades):
        client = TestClient(app_with_trades)
        resp = client.get(
            "/analytics/strategies/rsi/symbols", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        symbols = [s["symbol"] for s in data]
        assert "AAPL" in symbols
        assert "TSLA" in symbols
