"""Tests for strategy health API routes."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from config import Config
from storage.db import init_db
from storage.strategy_health import StrategyHealthStore


@pytest.fixture
def _env():
    os.environ["STA_API_KEY"] = "test-key"
    from api.auth import _get_settings

    _get_settings.cache_clear()
    yield
    _get_settings.cache_clear()


@pytest.fixture
async def app_with_health(_env):
    settings = Config(worker_mode=False, api_key="test-key")
    app = create_app(enable_agent_framework=False, config=settings)
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    app.state.db = db

    # Seed some health rows
    store = StrategyHealthStore(db)
    await store.upsert_status("rsi_agent", "normal")
    await store.upsert_status(
        "momentum_agent", "watchlist", trigger_reason="low expectancy"
    )
    await store.record_event(
        agent_name="momentum_agent",
        old_status="normal",
        new_status="watchlist",
        reason="expectancy below floor",
        metrics_snapshot={"expectancy": -0.002},
        actor="system",
    )

    yield app, store
    await db.close()


@pytest.fixture
async def app_with_health_engine(_env):
    """App fixture with a mock health engine on state."""
    settings = Config(worker_mode=False, api_key="test-key")
    app = create_app(enable_agent_framework=False, config=settings)
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    app.state.db = db

    from learning.strategy_health import StrategyHealthEngine

    mock_engine = MagicMock(spec=StrategyHealthEngine)
    mock_engine.recompute_all = AsyncMock(
        return_value={"rsi_agent": "normal", "momentum_agent": "watchlist"}
    )
    app.state.health_engine = mock_engine

    mock_runner = MagicMock()
    mock_runner.get_all_statuses = MagicMock(
        return_value={"rsi_agent": "RUNNING", "momentum_agent": "RUNNING"}
    )
    app.state.agent_runner = mock_runner

    yield app
    await db.close()


class TestListAllHealth:
    async def test_returns_all_statuses(self, app_with_health):
        app, _ = app_with_health
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/analytics/strategy-health", headers={"x-api-key": "test-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {row["agent_name"] for row in data}
        assert names == {"rsi_agent", "momentum_agent"}

    async def test_requires_api_key(self, app_with_health):
        app, _ = app_with_health
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/analytics/strategy-health")
        assert resp.status_code == 401

    async def test_empty_when_no_agents(self, _env):
        settings = Config(worker_mode=False, api_key="test-key")
        app = create_app(enable_agent_framework=False, config=settings)
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await init_db(db)
        app.state.db = db
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/analytics/strategy-health", headers={"x-api-key": "test-key"}
        )
        assert resp.status_code == 200
        assert resp.json() == []
        await db.close()


class TestGetAgentHealth:
    async def test_returns_status_and_events(self, app_with_health):
        app, _ = app_with_health
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/analytics/strategy-health/momentum_agent",
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "momentum_agent"
        assert data["status"]["status"] == "watchlist"
        assert len(data["recent_events"]) == 1
        assert data["recent_events"][0]["new_status"] == "watchlist"

    async def test_returns_none_status_for_unknown_agent(self, app_with_health):
        app, _ = app_with_health
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/analytics/strategy-health/unknown_agent",
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "unknown_agent"
        assert data["status"] is None
        assert data["recent_events"] == []


class TestOverrideAgentHealth:
    async def test_override_sets_status_and_records_event(self, app_with_health):
        app, store = app_with_health
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/analytics/strategy-health/rsi_agent/override",
            json={"status": "throttled", "reason": "manual throttle"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "throttled"
        assert data["actor"] == "operator"

        # Verify persisted
        row = await store.get_status("rsi_agent")
        assert row["status"] == "throttled"
        assert row["manual_override"] == "operator"

    async def test_override_invalid_status_returns_422(self, app_with_health):
        app, _ = app_with_health
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/analytics/strategy-health/rsi_agent/override",
            json={"status": "super_bad_status", "reason": "test"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 422

    async def test_override_requires_api_key(self, app_with_health):
        """Unauthenticated callers are rejected by the scope check (403), not
        by the legacy verify_api_key (which returned 401). The route has been
        migrated to require_scope('control:agents')."""
        app, _ = app_with_health
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/analytics/strategy-health/rsi_agent/override",
            json={"status": "retired", "reason": "test"},
        )
        assert resp.status_code == 403
        assert "control:agents" in resp.json()["detail"]

    async def test_override_all_valid_statuses(self, app_with_health):
        app, _ = app_with_health
        client = TestClient(app, raise_server_exceptions=True)
        for status in ("normal", "watchlist", "throttled", "shadow_only", "retired"):
            resp = client.post(
                "/analytics/strategy-health/rsi_agent/override",
                json={"status": status, "reason": "test"},
                headers={"x-api-key": "test-key"},
            )
            assert resp.status_code == 200, f"Failed for status: {status}"


class TestRecomputeHealth:
    async def test_recompute_calls_engine(self, app_with_health_engine):
        app = app_with_health_engine
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/analytics/strategy-health/recompute", headers={"x-api-key": "test-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["recomputed"] == 2
        assert "rsi_agent" in data["results"]

    async def test_recompute_returns_503_without_engine(self, _env):
        settings = Config(worker_mode=False, api_key="test-key")
        app = create_app(enable_agent_framework=False, config=settings)
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await init_db(db)
        app.state.db = db
        # No health_engine on state

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/analytics/strategy-health/recompute", headers={"x-api-key": "test-key"}
        )
        assert resp.status_code == 503
        await db.close()

    async def test_recompute_requires_api_key(self, app_with_health_engine):
        """Unauthenticated callers are rejected by the scope check (403), not
        by the legacy verify_api_key (which returned 401). The route has been
        migrated to require_scope('control:agents')."""
        app = app_with_health_engine
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/analytics/strategy-health/recompute")
        assert resp.status_code == 403
        assert "control:agents" in resp.json()["detail"]
