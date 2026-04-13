"""
Tests for rate limiter bucket key with verified identity.

Verifies that rate limiting buckets requests by verified agent name,
not by raw token value. Unknown tokens fall back to IP-based bucketing.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from fastapi import Request

from api.identity.dependencies import Identity


@pytest_asyncio.fixture
async def app_with_limiter():
    from fastapi import FastAPI
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from api.middleware.limiter import get_limiter

    app = FastAPI()
    app.state.limiter = get_limiter()

    @app.get("/test")
    @app.state.limiter.limit("10/minute")
    async def test_endpoint(request: Request):
        return {"ok": True}

    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    mock_store = AsyncMock()
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.token_hash = "real-token-hash"
    mock_store.list_active = AsyncMock(return_value=[mock_agent])
    app.state.identity_store = mock_store

    return app


@pytest.mark.asyncio
async def test_verified_agent_buckets_by_name(app_with_limiter):
    """Verified agent token should bucket by agent name, not token value."""
    from api.identity.tokens import hash_token

    real_token = "test-token-123"
    app_with_limiter.state.identity_store.list_active.return_value[
        0
    ].token_hash = hash_token(real_token)

    transport = ASGITransport(app=app_with_limiter)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp1 = await client.get("/test", headers={"X-Agent-Token": real_token})
        assert resp1.status_code == 200


@pytest.mark.asyncio
async def test_unknown_token_buckets_anon(app_with_limiter):
    """Unknown/invalid token should fall back to IP-based bucketing."""
    transport = ASGITransport(app=app_with_limiter)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/test", headers={"X-Agent-Token": "unknown-fake-token"}
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_rotation_resets_to_ip_bucket():
    """Rotating fake tokens should not reset the rate limit bucket."""
    from api.middleware.limiter import agent_identity_key_func

    mock_request = MagicMock()
    mock_request.headers = {"X-Agent-Token": "rotating-token-1"}
    mock_request.app.state.identity_store = AsyncMock()
    mock_request.app.state.identity_store.list_active = AsyncMock(return_value=[])

    key1 = await agent_identity_key_func(mock_request)

    mock_request.headers = {"X-Agent-Token": "rotating-token-2"}
    key2 = await agent_identity_key_func(mock_request)

    assert key1.startswith("tier:anon:")
    assert key2.startswith("tier:anon:")
    assert key1 == key2


@pytest.mark.asyncio
async def test_verified_agent_buckets_consistently():
    """Same verified agent with same token should always get same bucket."""
    from api.identity.tokens import hash_token, generate_token
    from api.middleware.limiter import agent_identity_key_func

    # Generate a properly formatted agent token
    agent_token = generate_token("consistent-agent")
    mock_store = AsyncMock()
    mock_agent = MagicMock()
    mock_agent.name = "consistent-agent"
    mock_agent.token_hash = hash_token(agent_token)
    mock_agent.revoked_at = None
    mock_store.get_by_name = AsyncMock(return_value=mock_agent)

    mock_request = MagicMock()
    mock_request.headers = {"X-Agent-Token": agent_token}
    mock_request.app.state.identity_store = mock_store

    key1 = await agent_identity_key_func(mock_request)
    key2 = await agent_identity_key_func(mock_request)

    assert key1 == key2 == "tier:agent:consistent-agent"
