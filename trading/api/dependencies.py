# trading/api/dependencies.py
"""
Hybrid authentication dependencies for FastAPI.

Supports both JWT tokens and legacy amc_* tokens.
"""

from fastapi import Depends, HTTPException, Header, Request
import os

# Import shared auth module - path setup happens at app startup (main.py)
from shared.auth.validate import validate_token, TokenValidationError

from .services.memory_registry import memory_registry, MemoryRegistry
from broker.interfaces import Broker


# Module-level singletons for risk engine and analytics (set at startup)
_risk_engine = None
_risk_analytics = None


def set_risk_engine(engine):
    """Set the risk engine singleton. Called at app startup."""
    global _risk_engine
    _risk_engine = engine


def set_risk_analytics(analytics):
    """Set the risk analytics singleton. Called at app startup."""
    global _risk_analytics
    _risk_analytics = analytics


def get_risk_engine(request: Request = None):
    """Get risk engine from app state or module-level singleton."""
    if request is not None:
        engine = getattr(request.app.state, "risk_engine", None)
        if engine is not None:
            return engine
    global _risk_engine
    if _risk_engine is None:
        raise HTTPException(500, "Risk engine not initialized")
    return _risk_engine


def get_risk_analytics(request: Request = None):
    """Get risk analytics from app state or module-level singleton."""
    if request is not None:
        analytics = getattr(request.app.state, "risk_analytics", None)
        if analytics is not None:
            return analytics
    global _risk_analytics
    if _risk_analytics is None:
        return None  # Return None instead of raising, let caller handle
    return _risk_analytics


def get_broker(request: Request) -> Broker:
    """Get broker from app state."""
    broker = getattr(request.app.state, "broker", None)
    if broker is None:
        raise HTTPException(500, "Broker not initialized")
    return broker


def get_memory_registry() -> MemoryRegistry:
    return memory_registry


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


async def check_kill_switch(request: Request):
    """
    Dependency to block mutations if the global kill-switch is active in Redis.
    """
    redis = get_redis(request)
    is_active = await redis.get("kill_switch:active")
    if is_active == "true":
        # Check if route is allowlisted (only GET usually, but double check)
        if request.method != "GET":
            raise HTTPException(
                status_code=503, 
                detail="Trading is currently halted via global kill-switch"
            )


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
