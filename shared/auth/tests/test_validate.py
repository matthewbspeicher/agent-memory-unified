# shared/auth/tests/test_validate.py
import pytest
import jwt
import time
from shared.auth.validate import validate_token, TokenValidationError
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_validates_valid_jwt():
    """Valid JWT passes validation."""
    secret = "test-secret-key"
    payload = {
        "sub": "agent-123",
        "type": "agent",
        "scopes": ["memories:write"],
        "iat": int(time.time()),
        "exp": int(time.time()) + 900,
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    # Mock Redis (not revoked)
    redis = AsyncMock()
    redis.sismember = AsyncMock(return_value=False)

    # Mock DB (not needed for JWT)
    db = AsyncMock()

    result = await validate_token(token, redis, db, jwt_secret=secret)

    assert result["sub"] == "agent-123"
    assert result["type"] == "agent"

@pytest.mark.asyncio
async def test_rejects_expired_jwt():
    """Expired JWT raises error."""
    secret = "test-secret-key"
    payload = {
        "sub": "agent-123",
        "exp": int(time.time()) - 3600,  # Expired
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    redis = AsyncMock()
    db = AsyncMock()

    with pytest.raises(TokenValidationError, match="expired"):
        await validate_token(token, redis, db, jwt_secret=secret)

@pytest.mark.asyncio
async def test_rejects_revoked_jwt():
    """Revoked JWT raises error."""
    secret = "test-secret-key"
    payload = {
        "sub": "agent-123",
        "exp": int(time.time()) + 900,
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    # Mock Redis (wildcard revoked)
    redis = AsyncMock()
    redis.sismember = AsyncMock(side_effect=lambda key, member: member == "*")

    db = AsyncMock()

    with pytest.raises(TokenValidationError, match="revoked"):
        await validate_token(token, redis, db, jwt_secret=secret)

@pytest.mark.asyncio
async def test_fallback_to_legacy_token():
    """amc_* tokens fall back to database lookup."""
    redis = AsyncMock()
    redis.setex = AsyncMock()

    # Mock DB returns agent
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={
        "id": "agent-123",
        "name": "TestBot",
        "scopes": ["memories:write"],
        "is_active": True,
    })

    token = "amc_legacy_token_12345"

    result = await validate_token(token, redis, db)

    assert result["sub"] == "agent-123"
    assert result["type"] == "agent"
    assert db.fetchrow.called
