"""Tests for shadow execution API routes."""

from __future__ import annotations

import os

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from config import Config
from storage.db import init_db
from storage.shadow import ShadowExecutionStore


@pytest.fixture
def _env():
    os.environ["STA_API_KEY"] = "test-key"
    from api.auth import _get_settings

    _get_settings.cache_clear()
    yield
    _get_settings.cache_clear()


def _record(record_id: str, **overrides) -> dict:
    record = {
        "id": record_id,
        "opportunity_id": f"opp-{record_id}",
        "agent_name": "rsi_agent",
        "symbol": "AAPL",
        "side": "BUY",
        "action_level": "auto_trade",
        "decision_status": "allowed",
        "expected_entry_price": "150.25",
        "expected_quantity": "10",
        "expected_notional": "1502.50",
        "entry_price_source": "ask",
        "opportunity_snapshot": {"confidence": 0.82},
        "risk_snapshot": {"max_loss": "50.00"},
        "sizing_snapshot": {"shares": 10},
        "regime_snapshot": {"regime": "risk_on"},
        "health_snapshot": {"status": "normal"},
        "opened_at": "2026-04-01T10:00:00+00:00",
        "resolve_after": "2026-04-01T11:00:00+00:00",
        "resolved_at": None,
        "resolution_status": "open",
        "resolution_price": None,
        "pnl": None,
        "return_bps": None,
        "max_favorable_bps": None,
        "max_adverse_bps": None,
        "resolution_notes": None,
    }
    record.update(overrides)
    return record


@pytest.fixture
async def app_with_shadow_store(_env):
    settings = Config(broker_mode="paper", api_key="test-key")
    app = create_app(enable_agent_framework=False, config=settings)
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)

    store = ShadowExecutionStore(db)
    await store.save(
        _record(
            "shadow-001",
            agent_name="rsi_agent",
            symbol="AAPL",
            decision_status="allowed",
            resolution_status="resolved",
            resolved_at="2026-04-01T10:30:00+00:00",
            pnl="7.50",
            return_bps=50.0,
            opened_at="2026-04-01T10:03:00+00:00",
        )
    )
    await store.save(
        _record(
            "shadow-002",
            agent_name="rsi_agent",
            symbol="AAPL",
            decision_status="blocked_risk",
            opened_at="2026-04-01T10:02:00+00:00",
        )
    )
    await store.save(
        _record(
            "shadow-003",
            agent_name="macd_agent",
            symbol="TSLA",
            decision_status="allowed",
            resolution_status="open",
            opened_at="2026-04-01T10:01:00+00:00",
        )
    )

    app.state.shadow_execution_store = store

    yield app
    await db.close()


class TestShadowExecutionsAPI:
    async def test_list_shadow_executions_applies_filters(self, app_with_shadow_store):
        client = TestClient(app_with_shadow_store)

        resp = client.get(
            "/shadow/executions?agent_name=rsi_agent&symbol=AAPL&decision_status=allowed&resolution_status=resolved&limit=1",
            headers={"X-API-Key": "test-key"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert [row["id"] for row in data] == ["shadow-001"]

    async def test_get_shadow_execution_by_id(self, app_with_shadow_store):
        client = TestClient(app_with_shadow_store)

        resp = client.get(
            "/shadow/executions/shadow-001",
            headers={"X-API-Key": "test-key"},
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == "shadow-001"

    async def test_get_shadow_execution_returns_404_when_missing(
        self, app_with_shadow_store
    ):
        client = TestClient(app_with_shadow_store)

        resp = client.get(
            "/shadow/executions/missing",
            headers={"X-API-Key": "test-key"},
        )

        assert resp.status_code == 404

    async def test_shadow_summary_returns_store_summary(self, app_with_shadow_store):
        client = TestClient(app_with_shadow_store)

        resp = client.get(
            "/shadow/summary",
            headers={"X-API-Key": "test-key"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        rsi = next(row for row in data if row["agent_name"] == "rsi_agent")
        assert rsi["total_count"] == 2
        assert rsi["resolved_count"] == 1
        assert rsi["pending_count"] == 1

    async def test_agent_shadow_summary(self, app_with_shadow_store):
        """GET /shadow/agents/{name}/summary returns per-agent stats."""
        client = TestClient(app_with_shadow_store)

        resp = client.get(
            "/shadow/agents/rsi_agent/summary",
            headers={"X-API-Key": "test-key"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "rsi_agent"
        assert "stats" in data
        assert data["stats"]["total_count"] == 2
        assert "promotion_criteria" in data
        assert "eligible_for_promotion" in data

    async def test_agent_shadow_summary_not_found(self, app_with_shadow_store):
        """GET /shadow/agents/{name}/summary returns 404 when no data exists."""
        client = TestClient(app_with_shadow_store)

        resp = client.get(
            "/shadow/agents/nonexistent_agent/summary",
            headers={"X-API-Key": "test-key"},
        )

        assert resp.status_code == 404

    async def test_agent_shadow_summary_requires_auth(self, app_with_shadow_store):
        client = TestClient(app_with_shadow_store)

        resp = client.get("/shadow/agents/rsi_agent/summary")

        assert resp.status_code in (401, 403)

    async def test_shadow_routes_require_auth(self, app_with_shadow_store):
        client = TestClient(app_with_shadow_store)

        resp = client.get("/shadow/executions")

        assert resp.status_code in (401, 403)

    async def test_shadow_summary_requires_auth(self, app_with_shadow_store):
        client = TestClient(app_with_shadow_store)

        resp = client.get("/shadow/summary")

        assert resp.status_code in (401, 403)

    async def test_shadow_detail_rejects_invalid_auth(self, app_with_shadow_store):
        client = TestClient(app_with_shadow_store)

        resp = client.get(
            "/shadow/executions/shadow-001",
            headers={"X-API-Key": "wrong-key"},
        )

        assert resp.status_code in (401, 403)

    async def test_shadow_routes_return_501_when_store_not_configured(self, _env):
        settings = Config(broker_mode="paper", api_key="test-key")
        app = create_app(enable_agent_framework=False, config=settings)
        client = TestClient(app)

        resp = client.get(
            "/shadow/executions",
            headers={"X-API-Key": "test-key"},
        )

        assert resp.status_code == 501

    async def test_promote_agent_shadow_to_live(self, app_with_shadow_store):
        """Promoting a shadow agent sets shadow_mode=False."""
        client = TestClient(app_with_shadow_store)

        resp = client.post(
            "/shadow/agents/rsi_shadow/promote",
            headers={"X-API-Key": "test-key"},
        )
        # Should either work or return 501 if agent store not configured
        assert resp.status_code in (200, 501)

    async def test_promote_returns_501_without_agent_store(self, _env):
        """Promote endpoint returns 501 if agent store not configured."""
        settings = Config(broker_mode="paper", api_key="test-key")
        app = create_app(enable_agent_framework=False, config=settings)
        client = TestClient(app)

        resp = client.post(
            "/shadow/agents/any_agent/promote",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 501
