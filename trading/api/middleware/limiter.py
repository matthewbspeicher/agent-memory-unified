import logging
import hashlib
from fastapi import Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
import os

from api.identity.tokens import verify_token

logger = logging.getLogger(__name__)

ANON_ALLOWLIST = {
    "/engine/v1/health",
    "/engine/v1/health/live",
    "/engine/v1/health/ready",
    "/metrics",
    "/engine/v1/bittensor/kg/stats",
}


async def agent_identity_key_func(request: Request) -> str:
    """
    Custom key function for rate limiting with verified identity.

    Tiers:
    1. Verified Agent: X-Agent-Token present and valid → bucket by agent name
    2. Master: X-API-Key present and matches config → bucket by master
    3. Anonymous/Unverified: No valid auth → bucket by IP
    """
    agent_token = request.headers.get("X-Agent-Token")
    if agent_token:
        store = getattr(request.app.state, "identity_store", None)
        if store:
            agents = await store.list_active()
            for agent in agents:
                if verify_token(agent_token, agent.token_hash):
                    return f"tier:agent:{agent.name}"

    api_key = request.headers.get("X-API-Key")
    if api_key:
        config = getattr(request.app.state, "config", None)
        if config and api_key == getattr(config, "api_key", None):
            key_hash = hashlib.md5(api_key.encode()).hexdigest()[:8]
            return f"tier:master:{key_hash}"

    ip = get_remote_address(request)
    return f"tier:anon:{ip}"


async def get_tier_limit(request: Request) -> str:
    agent_token = request.headers.get("X-Agent-Token")
    if agent_token:
        store = getattr(request.app.state, "identity_store", None)
        if store:
            agents = await store.list_active()
            for agent in agents:
                if verify_token(agent_token, agent.token_hash):
                    return "60/minute"
        return "10/minute"

    api_key = request.headers.get("X-API-Key")
    if api_key:
        config = getattr(request.app.state, "config", None)
        if config and api_key == getattr(config, "api_key", None):
            return "300/minute"

    return "10/minute"


def get_limiter(redis_url: str | None = None) -> Limiter:
    """
    Initialize and return the slowapi Limiter.

    Uses get_tier_limit as the dynamic default so each identity tier
    (anonymous / agent / master) gets its own rate ceiling.
    """
    storage_uri = redis_url if redis_url else "memory://"
    if storage_uri.startswith("redis://") and not storage_uri.startswith(
        "async+redis://"
    ):
        storage_uri = storage_uri.replace("redis://", "async+redis://")

    return Limiter(
        key_func=agent_identity_key_func,
        storage_uri=storage_uri,
        strategy="moving-window",
        default_limits=[get_tier_limit],
    )


async def anon_read_only_guard(request: Request):
    """
    Dependency/Guard to ensure anonymous requests only hit the allowlist.
    """
    # If authenticated, skip
    if request.headers.get("X-Agent-Token") or request.headers.get("X-API-Key"):
        return

    path = request.url.path
    if path not in ANON_ALLOWLIST:
        # Check if it's a read-only path (GET)
        if request.method != "GET":
            raise HTTPException(status_code=403, detail="Anonymous write access denied")

        # Optionally restrict to specific allowlist even for GET
        # For Phase A, we stick to the explicit allowlist for Anon.
        if not any(path.startswith(p) for p in ANON_ALLOWLIST):
            raise HTTPException(
                status_code=403, detail="Anonymous access denied for this endpoint"
            )
