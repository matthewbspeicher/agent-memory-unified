"""Tests for confidence calibration analytics API routes."""
from __future__ import annotations

import os

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from config import Config
from storage.db import init_db
from storage.confidence_calibration import ConfidenceCalibrationStore


@pytest.fixture
def _env():
    os.environ["STA_API_KEY"] = "test-key"
    from api.auth import _get_settings
    _get_settings.cache_clear()
    yield
    _get_settings.cache_clear()


def _make_cal_row(**overrides) -> dict:
    defaults = {
        "trade_count": 30,
        "win_rate": 0.65,
        "avg_net_pnl": "40.00",
        "avg_net_return_pct": 0.012,
        "expectancy": "0.012000",
        "profit_factor": 1.8,
        "max_drawdown": "-0.025",
        "calibrated_score": 0.0072,
        "sample_quality": "usable",
    }
    defaults.update(overrides)
    return defaults


@pytest.fixture
async def app_with_calibration(_env):
    settings = Config(broker_mode="paper", api_key="test-key")
    app = create_app(enable_agent_framework=False, config=settings)
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    app.state.db = db

    store = ConfidenceCalibrationStore(db)
    # Insert calibration rows for two strategies, multiple buckets, multiple windows
    for window_label in ("30d", "90d", "all"):
        await store.upsert(
            agent_name="rsi_agent",
            confidence_bucket="0.70-0.80",
            window_label=window_label,
            **_make_cal_row(trade_count=30),
        )
        await store.upsert(
            agent_name="rsi_agent",
            confidence_bucket="0.80-0.90",
            window_label=window_label,
            **_make_cal_row(trade_count=55, win_rate=0.72, sample_quality="strong"),
        )
    await store.upsert(
        agent_name="momentum_agent",
        confidence_bucket="0.60-0.70",
        window_label="all",
        **_make_cal_row(trade_count=12, sample_quality="weak"),
    )

    yield app
    await db.close()


class TestListStrategiesCalibration:
    async def test_returns_all_rows_default_window(self, app_with_calibration):
        client = TestClient(app_with_calibration)
        resp = client.get("/analytics/confidence/strategies", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # window=all → rsi_agent (2 buckets) + momentum_agent (1 bucket)
        assert len(data) == 3

    async def test_window_filter_30d(self, app_with_calibration):
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/strategies?window=30d",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # momentum_agent only has 'all', not '30d'
        agents = {r["agent_name"] for r in data}
        assert "rsi_agent" in agents
        assert "momentum_agent" not in agents

    async def test_requires_auth(self, app_with_calibration):
        client = TestClient(app_with_calibration)
        resp = client.get("/analytics/confidence/strategies")
        assert resp.status_code in (401, 403)

    async def test_invalid_window_rejected(self, app_with_calibration):
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/strategies?window=7d",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 422


class TestGetStrategyCalibration:
    async def test_returns_buckets_for_strategy(self, app_with_calibration):
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/rsi_agent",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2  # 2 buckets in "all" window

    async def test_window_filter(self, app_with_calibration):
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/rsi_agent?window=30d",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["window_label"] == "30d" for r in data)

    async def test_unknown_strategy_returns_empty_list(self, app_with_calibration):
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/nonexistent_agent",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_requires_auth(self, app_with_calibration):
        client = TestClient(app_with_calibration)
        resp = client.get("/analytics/confidence/rsi_agent")
        assert resp.status_code in (401, 403)


class TestGetRecommendation:
    async def test_returns_recommendation_fields(self, app_with_calibration):
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/rsi_agent/recommendation?confidence=0.75",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "rsi_agent"
        assert data["bucket"] == "0.70-0.80"
        assert "sample_quality" in data
        assert "trade_count" in data
        assert "multiplier" in data
        assert "would_reject" in data
        assert "reason" in data
        assert isinstance(data["multiplier"], float)
        assert isinstance(data["would_reject"], bool)

    async def test_multiplier_range(self, app_with_calibration):
        """Multiplier must be in [0.25, 1.25]."""
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/rsi_agent/recommendation?confidence=0.75",
            headers={"X-API-Key": "test-key"},
        )
        data = resp.json()
        assert 0.25 <= data["multiplier"] <= 1.25

    async def test_unknown_strategy_returns_fallback(self, app_with_calibration):
        """No calibration data → conservative fallback, no rejection."""
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/unknown_agent/recommendation?confidence=0.85",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["would_reject"] is False
        assert data["trade_count"] == 0
        assert "No calibration data" in data["reason"]

    async def test_high_confidence_strong_sample(self, app_with_calibration):
        """0.85 maps to 0.80-0.90 bucket — 55 trades (strong), positive expectancy."""
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/rsi_agent/recommendation?confidence=0.85",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["bucket"] == "0.80-0.90"
        assert data["sample_quality"] == "strong"
        assert data["would_reject"] is False

    async def test_confidence_required(self, app_with_calibration):
        """confidence query parameter is required."""
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/rsi_agent/recommendation",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 422

    async def test_confidence_clamped_validation(self, app_with_calibration):
        """confidence must be in [0, 1]."""
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/rsi_agent/recommendation?confidence=1.5",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 422

    async def test_requires_auth(self, app_with_calibration):
        client = TestClient(app_with_calibration)
        resp = client.get(
            "/analytics/confidence/rsi_agent/recommendation?confidence=0.75"
        )
        assert resp.status_code in (401, 403)

    async def test_window_param_respected(self, app_with_calibration):
        """Different windows can return different calibration data."""
        client = TestClient(app_with_calibration)
        resp_all = client.get(
            "/analytics/confidence/rsi_agent/recommendation?confidence=0.75&window=all",
            headers={"X-API-Key": "test-key"},
        )
        resp_30d = client.get(
            "/analytics/confidence/rsi_agent/recommendation?confidence=0.75&window=30d",
            headers={"X-API-Key": "test-key"},
        )
        assert resp_all.status_code == 200
        assert resp_30d.status_code == 200
        assert resp_all.json()["window"] == "all"
        assert resp_30d.json()["window"] == "30d"
