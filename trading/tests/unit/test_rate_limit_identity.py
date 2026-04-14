"""
Tests for rate limiter bucket key with verified identity.

Verifies that rate limiting buckets requests by verified agent name,
not by raw token value. Unknown tokens fall back to IP-based bucketing.

Architecture note: slowapi 0.1.9 calls key_func synchronously, so
identity resolution is performed in RateLimitIdentityMiddleware and
cached on request.state. The sync key_func reads from that cache.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from fastapi import Request


@pytest_asyncio.fixture
async def app_with_limiter():
    from fastapi import FastAPI
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from api.middleware.limiter import (
        RateLimitIdentityMiddleware,
        get_limiter,
    )

    app = FastAPI()
    app.state.limiter = get_limiter()

    @app.get("/test")
    @app.state.limiter.limit("10/minute")
    async def test_endpoint(request: Request):
        return {"ok": True, "key": request.state.rate_limit_identity.key}

    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(RateLimitIdentityMiddleware)

    mock_store = AsyncMock()
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.token_hash = "real-token-hash"
    mock_agent.revoked_at = None
    mock_store.get_by_name = AsyncMock(return_value=mock_agent)
    app.state.identity_store = mock_store

    return app


@pytest.mark.asyncio
async def test_verified_agent_buckets_by_name(app_with_limiter):
    """Verified agent token should bucket by agent name, not token value."""
    from api.identity.tokens import hash_token, generate_token

    real_token = generate_token("test-agent")
    app_with_limiter.state.identity_store.get_by_name.return_value.token_hash = (
        hash_token(real_token)
    )

    transport = ASGITransport(app=app_with_limiter)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/test", headers={"X-Agent-Token": real_token})
        assert resp.status_code == 200
        assert resp.json()["key"] == "tier:agent:test-agent"


@pytest.mark.asyncio
async def test_unknown_token_does_not_grant_agent_tier(app_with_limiter):
    """Unknown/invalid token should NOT return an agent tier key."""
    app_with_limiter.state.identity_store.get_by_name = AsyncMock(return_value=None)

    transport = ASGITransport(app=app_with_limiter)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/test", headers={"X-Agent-Token": "amu_unknown.fake-sig"}
        )
        assert resp.status_code == 200
        key = resp.json()["key"]
        assert not key.startswith("tier:agent:")


# --- Unit tests for _resolve_identity (the core logic) ---


@pytest.mark.asyncio
async def test_resolve_identity_rotating_fake_tokens_share_ip_bucket():
    """Rotating fake tokens should all produce the same IP-based key."""
    from api.middleware.limiter import _resolve_identity

    mock_store = AsyncMock()
    mock_store.get_by_name = AsyncMock(return_value=None)

    mock_request = MagicMock()
    mock_request.app.state.identity_store = mock_store
    mock_request.client = MagicMock(host="1.2.3.4")

    mock_request.headers = {"X-Agent-Token": "amu_rotating1.sig"}
    id1 = await _resolve_identity(mock_request)
    mock_request.headers = {"X-Agent-Token": "amu_rotating2.sig"}
    id2 = await _resolve_identity(mock_request)

    # Unverified tokens share an IP bucket, not per-token buckets
    assert id1.key == id2.key


@pytest.mark.asyncio
async def test_resolve_identity_verified_agent_consistent_bucket():
    """Same verified agent with same token should always resolve to same key."""
    from api.identity.tokens import hash_token, generate_token
    from api.middleware.limiter import _resolve_identity

    agent_token = generate_token("consistent-agent")
    mock_agent = MagicMock()
    mock_agent.name = "consistent-agent"
    mock_agent.token_hash = hash_token(agent_token)
    mock_agent.revoked_at = None
    mock_store = AsyncMock()
    mock_store.get_by_name = AsyncMock(return_value=mock_agent)

    mock_request = MagicMock()
    mock_request.headers = {"X-Agent-Token": agent_token}
    mock_request.app.state.identity_store = mock_store

    id1 = await _resolve_identity(mock_request)
    id2 = await _resolve_identity(mock_request)

    assert id1.key == id2.key == "tier:agent:consistent-agent"
    assert id1.limit == "60/minute"


def test_sync_key_func_reads_request_state():
    """Sync key_func must read from request.state, no DB call."""
    from api.middleware.limiter import (
        RateLimitIdentity,
        agent_identity_key_func,
        get_tier_limit,
    )

    mock_request = MagicMock()
    mock_request.state.rate_limit_identity = RateLimitIdentity(
        key="tier:agent:foo", limit="60/minute"
    )

    assert agent_identity_key_func(mock_request) == "tier:agent:foo"
    assert get_tier_limit(mock_request) == "60/minute"


def test_sync_key_func_fallback_when_middleware_missed():
    """If middleware didn't run, key_func falls back to IP-based anon bucket."""
    from api.middleware.limiter import agent_identity_key_func, get_tier_limit

    mock_request = MagicMock()
    # Simulate no rate_limit_identity on state
    del mock_request.state.rate_limit_identity
    mock_request.client = MagicMock(host="10.0.0.1")

    key = agent_identity_key_func(mock_request)
    assert key.startswith("tier:anon:")
    assert get_tier_limit(mock_request) == "10/minute"
