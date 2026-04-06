# api/tests/test_dependencies.py
"""Tests for FastAPI authentication dependencies."""
import pytest
from unittest.mock import AsyncMock
from fastapi import HTTPException

from api.dependencies import require_scope


@pytest.mark.asyncio
async def test_get_current_user_with_jwt():
    """Test authentication with valid JWT token."""
    # Mock Redis and DB
    redis = AsyncMock()
    redis.sismember = AsyncMock(return_value=False)

    db = AsyncMock()

    # Valid JWT token (simplified mock)
    token = "valid.jwt.token"
    authorization = f"Bearer {token}"

    # Mock the validate_token function to return user data
    import sys
    sys.path.insert(0, '/opt/homebrew/var/www/agent-memory-unified')

    # Patch validate_token
    from unittest.mock import patch
    with patch('shared.auth.validate.validate_token', new=AsyncMock(return_value={
        "sub": "test-agent-id",
        "type": "agent",
        "scopes": ["memories:write", "trading:execute"]
    })):
        from api.dependencies import get_current_user

        user = await get_current_user(
            authorization=authorization,
            redis=redis,
            db=db
        )

        assert user["sub"] == "test-agent-id"
        assert user["type"] == "agent"
        assert "trading:execute" in user["scopes"]


@pytest.mark.asyncio
async def test_get_current_user_with_legacy_token():
    """Test authentication with legacy amc_* token."""
    redis = AsyncMock()
    redis.sismember = AsyncMock(return_value=False)
    redis.get = AsyncMock(return_value=None)  # No cache hit
    redis.setex = AsyncMock()

    # Mock database response
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={
        "id": "legacy-agent-id",
        "name": "Legacy Agent",
        "scopes": ["memories:write"],
        "is_active": True
    })

    token = "amc_legacy_token_12345"
    authorization = f"Bearer {token}"

    from unittest.mock import patch
    with patch('shared.auth.validate.validate_token', new=AsyncMock(return_value={
        "sub": "legacy-agent-id",
        "type": "agent",
        "scopes": ["memories:write"]
    })):
        from api.dependencies import get_current_user

        user = await get_current_user(
            authorization=authorization,
            redis=redis,
            db=db
        )

        assert user["sub"] == "legacy-agent-id"
        assert user["type"] == "agent"


@pytest.mark.asyncio
async def test_get_current_user_invalid_header():
    """Test authentication with invalid authorization header."""
    redis = AsyncMock()
    db = AsyncMock()

    authorization = "InvalidFormat token"

    from api.dependencies import get_current_user

    with pytest.raises(HTTPException) as exc:
        await get_current_user(
            authorization=authorization,
            redis=redis,
            db=db
        )

    assert exc.value.status_code == 401
    assert "Invalid authorization header" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_current_user_missing_jwt_secret():
    """Test authentication fails when JWT_SECRET not configured."""
    redis = AsyncMock()
    db = AsyncMock()

    authorization = "Bearer valid.jwt.token"

    import os

    # Temporarily remove JWT_SECRET
    original_secret = os.environ.get("JWT_SECRET")
    if "JWT_SECRET" in os.environ:
        del os.environ["JWT_SECRET"]

    try:
        from api.dependencies import get_current_user

        with pytest.raises(HTTPException) as exc:
            await get_current_user(
                authorization=authorization,
                redis=redis,
                db=db
            )

        assert exc.value.status_code == 500
        assert "JWT_SECRET not configured" in str(exc.value.detail)
    finally:
        # Restore JWT_SECRET
        if original_secret:
            os.environ["JWT_SECRET"] = original_secret


@pytest.mark.asyncio
async def test_require_scope_with_valid_scope():
    """Test scope checking with valid scope."""
    user = {
        "sub": "test-agent",
        "type": "agent",
        "scopes": ["memories:write", "trading:execute"]
    }

    # Create the dependency
    check_fn = require_scope("trading:execute")

    # Call it with the user
    result = await check_fn(user=user)

    assert result == user


@pytest.mark.asyncio
async def test_require_scope_with_missing_scope():
    """Test scope checking with missing required scope."""
    user = {
        "sub": "test-agent",
        "type": "agent",
        "scopes": ["memories:write"]  # Missing trading:execute
    }

    check_fn = require_scope("trading:execute")

    with pytest.raises(HTTPException) as exc:
        await check_fn(user=user)

    assert exc.value.status_code == 403
    assert "Missing scope: trading:execute" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_require_scope_with_empty_scopes():
    """Test scope checking when user has no scopes."""
    user = {
        "sub": "test-agent",
        "type": "agent",
        "scopes": []
    }

    check_fn = require_scope("trading:execute")

    with pytest.raises(HTTPException) as exc:
        await check_fn(user=user)

    assert exc.value.status_code == 403
