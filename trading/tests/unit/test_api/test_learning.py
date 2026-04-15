import os
import pytest
import aiosqlite
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from storage.db import init_db
from storage.pnl import TrackedPositionStore
from storage.performance import PerformanceStore
from storage.agent_registry import AgentStore
from api.routes.learning import create_learning_router

AUTH_HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
async def client():
    os.environ["STA_API_KEY"] = "test-key"
    # Clear lru_cache so the test key is picked up
    from api.auth import _get_settings

    _get_settings.cache_clear()

    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)

    pnl_store = TrackedPositionStore(db)
    perf_store = PerformanceStore(db)
    agent_store = AgentStore(db)

    # Seed a test agent so trust updates work
    await agent_store.create(
        {"name": "rsi_scanner", "strategy": "rsi", "status": "active"}
    )

    router = create_learning_router(pnl_store, perf_store, agent_store)
    app = FastAPI()
    app.include_router(router)

    from api.identity.dependencies import resolve_identity, Identity

    async def _admin_identity():
        return Identity(name="master", scopes=frozenset(["admin", "*"]), tier="admin")

    app.dependency_overrides[resolve_identity] = _admin_identity

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    await db.close()


async def test_get_pnl_empty(client):
    resp = await client.get("/api/agents/rsi_scanner/pnl", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_put_trust_level(client):
    resp = await client.put(
        "/api/agents/rsi_scanner/trust",
        json={"trust_level": "assisted"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent"] == "rsi_scanner"
    assert data["trust_level"] == "assisted"


async def test_get_trust_history(client):
    await client.put(
        "/api/agents/rsi_scanner/trust",
        json={"trust_level": "assisted"},
        headers=AUTH_HEADERS,
    )
    resp = await client.get(
        "/api/agents/rsi_scanner/trust/history", headers=AUTH_HEADERS
    )
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) == 1
    assert history[0]["new_level"] == "assisted"
    assert history[0]["changed_by"] == "rest_api"


async def test_get_performance_empty(client):
    resp = await client.get("/api/agents/rsi_scanner/performance", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == []
