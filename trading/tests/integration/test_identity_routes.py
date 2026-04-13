import pytest
import os
import asyncpg
import httpx
from fastapi import FastAPI
from api.identity.tokens import generate_token, hash_token
from api.identity.store import IdentityStore


@pytest.fixture
def master_api_key():
    return "test-master-key-12345"


async def _create_app_with_identity(master_api_key, postgres_dsn):
    pool = await asyncpg.create_pool(postgres_dsn, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE identity.agents, identity.audit_log CASCADE")

    store = IdentityStore(pool)

    app = FastAPI()
    app.state.identity_store = store
    app.state.config = type("Config", (), {"api_key": master_api_key})()

    from api.routes.identity import router as identity_router

    app.include_router(identity_router)

    return app, store, pool


@pytest.fixture
async def identity_client(master_api_key, postgres_dsn):
    app, store, pool = await _create_app_with_identity(master_api_key, postgres_dsn)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["X-API-Key"] = master_api_key
        yield client
    await pool.close()


@pytest.fixture
async def anonymous_identity_client(master_api_key, postgres_dsn):
    app, store, pool = await _create_app_with_identity(master_api_key, postgres_dsn)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await pool.close()


@pytest.fixture
async def anonymous_identity_client(master_api_key, postgres_dsn):
    app, store, pool = await _create_app_with_identity(master_api_key, postgres_dsn)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await pool.close()


@pytest.mark.asyncio
async def test_me_endpoint_returns_anonymous_when_no_auth(anonymous_identity_client):
    resp = await anonymous_identity_client.get("/api/v1/identity/me")
    assert resp.status_code == 200
    assert resp.json()["name"] == "anonymous"


@pytest.mark.asyncio
async def test_me_endpoint_with_master_key(identity_client):
    resp = await identity_client.get("/api/v1/identity/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "master"
    assert "admin" in data["scopes"]


@pytest.mark.asyncio
async def test_register_agent_returns_token_once(identity_client):
    resp = await identity_client.post(
        "/api/v1/identity/agents",
        json={"name": "test-agent-1", "tier": "verified", "scopes": ["read:arena"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test-agent-1"
    assert data["token"].startswith("amu_")
    assert "warning" in data


@pytest.mark.asyncio
async def test_register_agent_rejects_duplicate_name(identity_client):
    await identity_client.post(
        "/api/v1/identity/agents",
        json={"name": "unique-agent", "tier": "verified"},
    )
    resp = await identity_client.post(
        "/api/v1/identity/agents",
        json={"name": "unique-agent", "tier": "verified"},
    )
    assert resp.status_code == 400 or resp.status_code == 500


@pytest.mark.asyncio
async def test_revoke_agent_requires_admin(anonymous_identity_client):
    resp = await anonymous_identity_client.post(
        "/api/v1/identity/agents/some-agent/revoke",
        json={"reason": "test"},
    )
    assert resp.status_code == 403
