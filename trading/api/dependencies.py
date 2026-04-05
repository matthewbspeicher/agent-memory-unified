# trading/api/dependencies.py
"""
Hybrid authentication dependencies for FastAPI.

Supports both JWT tokens and legacy amc_* tokens.
"""
from fastapi import Depends, HTTPException, Header, Request
import os

# Import here to avoid circular dependency
import sys
sys.path.insert(0, '/opt/homebrew/var/www/agent-memory-unified')
from shared.auth.validate import validate_token, TokenValidationError


def get_redis(request: Request):
    """Get Redis connection from app state."""
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(500, "Redis not initialized")
    return redis


def get_db(request: Request):
    """Get database connection from app state."""
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(500, "Database not initialized")
    return db


async def get_current_user(
    authorization: str = Header(...),
    request: Request = None,
) -> dict:
    """
    Hybrid authentication dependency.

    Validates JWT or legacy amc_* tokens.
    Returns user dict with: sub (agent_id), type, scopes.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header")

    token = authorization.replace("Bearer ", "")

    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        raise HTTPException(500, "JWT_SECRET not configured")

    # Get Redis and DB from app state
    redis = get_redis(request)
    db = get_db(request)

    try:
        user = await validate_token(token, redis, db, jwt_secret=jwt_secret)
        return user
    except TokenValidationError as e:
        raise HTTPException(401, str(e))


def require_scope(required_scope: str):
    """
    Dependency factory for scope checking.

    Usage:
        @router.post("/trades", dependencies=[Depends(require_scope("trading:execute"))])

    Returns:
        A dependency function that checks if the user has the required scope.
    """
    async def check(user: dict = Depends(get_current_user)):
        scopes = user.get("scopes", [])
        if required_scope not in scopes:
            raise HTTPException(403, f"Missing scope: {required_scope}")
        return user
    return check
