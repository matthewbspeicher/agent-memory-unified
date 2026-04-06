"""Tests for signal-features API routes."""

from __future__ import annotations

import os

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from broker.models import AssetType
from api.app import create_app
from api.routes.signal_features import _row_to_opportunity
from config import Config
from storage.db import init_db
from storage.signal_features import SignalFeatureStore


@pytest.fixture
def _env():
    os.environ["STA_API_KEY"] = "test-key"
    from api.auth import _get_settings

    _get_settings.cache_clear()
    yield
    _get_settings.cache_clear()


@pytest.fixture
async def app_with_features(_env):
    settings = Config(broker_mode="paper", api_key="test-key")
    app = create_app(enable_agent_framework=False, config=settings)
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    app.state.db = db
    app.state.data_bus = None  # no live data bus in unit tests

    store = SignalFeatureStore(db)
    await store.upsert(
        "opp-001",
        agent_name="rsi_agent",
        symbol="AAPL",
        signal="rsi_oversold",
        confidence=0.85,
        opportunity_timestamp="2026-03-31T10:00:00+00:00",
        captured_at="2026-03-31T10:00:01+00:00",
        feature_version="1.0",
        rsi_14=28.5,
        sma_20=172.0,
        atr_14=3.2,
        capture_status="captured",
    )
    await store.upsert(
        "opp-002",
        agent_name="macd_agent",
        symbol="TSLA",
        signal="macd_cross",
        confidence=0.72,
        opportunity_timestamp="2026-03-31T11:00:00+00:00",
        captured_at="2026-03-31T11:00:01+00:00",
        feature_version="1.0",
        rsi_14=55.0,
        capture_status="captured",
    )
    await store.upsert(
        "opp-003",
        agent_name="rsi_agent",
        symbol="MSFT",
        signal="rsi_oversold",
        confidence=0.78,
        opportunity_timestamp="2026-03-31T12:00:00+00:00",
        captured_at="2026-03-31T12:00:01+00:00",
        feature_version="1.0",
        capture_status="partial",
    )

    yield app
    await db.close()


class TestGetSignalFeatures:
    def test_get_by_opportunity_id(self, app_with_features):
        client = TestClient(app_with_features)
        resp = client.get(
            "/analytics/signal-features/opp-001", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["opportunity_id"] == "opp-001"
        assert data["agent_name"] == "rsi_agent"
        assert data["rsi_14"] == pytest.approx(28.5)

    def test_get_returns_404_for_missing(self, app_with_features):
        client = TestClient(app_with_features)
        resp = client.get(
            "/analytics/signal-features/no-such-opp", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 404

    def test_get_requires_auth(self, app_with_features):
        client = TestClient(app_with_features)
        resp = client.get("/analytics/signal-features/opp-001")
        assert resp.status_code in (401, 403)


class TestListSignalFeatures:
    def test_list_all(self, app_with_features):
        client = TestClient(app_with_features)
        resp = client.get(
            "/analytics/signal-features", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_filter_by_agent(self, app_with_features):
        client = TestClient(app_with_features)
        resp = client.get(
            "/analytics/signal-features?agent_name=rsi_agent",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(r["agent_name"] == "rsi_agent" for r in data)

    def test_filter_by_symbol(self, app_with_features):
        client = TestClient(app_with_features)
        resp = client.get(
            "/analytics/signal-features?symbol=TSLA",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "TSLA"

    def test_filter_by_signal(self, app_with_features):
        client = TestClient(app_with_features)
        resp = client.get(
            "/analytics/signal-features?signal=macd_cross",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["signal"] == "macd_cross"

    def test_limit_param(self, app_with_features):
        client = TestClient(app_with_features)
        resp = client.get(
            "/analytics/signal-features?limit=2",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_requires_auth(self, app_with_features):
        client = TestClient(app_with_features)
        resp = client.get("/analytics/signal-features")
        assert resp.status_code in (401, 403)


class TestBackfillRoute:
    def test_backfill_no_data_bus_returns_503(self, app_with_features):
        client = TestClient(app_with_features)
        resp = client.post(
            "/analytics/signal-features/backfill", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 503

    def test_backfill_requires_auth(self, app_with_features):
        client = TestClient(app_with_features)
        resp = client.post("/analytics/signal-features/backfill")
        assert resp.status_code in (401, 403)


class TestRowToOpportunity:
    def test_preserves_prediction_asset_type_from_data(self):
        opp = _row_to_opportunity(
            {
                "id": "opp-kalshi",
                "agent_name": "kalshi_agent",
                "symbol": "KXTEST-YES",
                "signal": "edge",
                "confidence": 0.74,
                "reasoning": "test",
                "status": "pending",
                "created_at": "2026-03-31T12:00:00+00:00",
                "data": '{"asset_type":"PREDICTION","broker_id":"kalshi"}',
            }
        )

        assert opp is not None
        assert opp.symbol.asset_type == AssetType.PREDICTION
        assert opp.broker_id == "kalshi"
