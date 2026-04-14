"""Rate-limit key + tier resolution for slowapi.

slowapi 0.1.9 calls `key_func(request)` synchronously from its internals
(extension.py:497), so an async key_func returns an unawaited coroutine
that slowapi then uses as the rate-limit key — silently breaking bucket
segmentation. The middleware below resolves identity once per request
and caches the resolved tier/limit on `request.state`. The sync key_func
and sync tier resolver read from that cache so slowapi's sync call path
gets a real string.
"""

import hashlib
import logging
from dataclasses import dataclass

from fastapi import HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from api.identity.tokens import verify_token

logger = logging.getLogger(__name__)

ANON_ALLOWLIST = {
    "/engine/v1/health",
    "/engine/v1/health/live",
    "/engine/v1/health/ready",
    "/metrics",
    "/engine/v1/bittensor/kg/stats",
}


@dataclass(frozen=True)
class RateLimitIdentity:
    """Resolved tier/key/limit for the current request — stashed on request.state."""

    key: str
    limit: str


async def _resolve_identity(request: Request) -> RateLimitIdentity:
    """Perform identity verification and return the tier key + limit string.

    Mirrors the previous async key_func + get_tier_limit behavior but returns
    both values in a single DB round-trip instead of two.
    """
    agent_token = request.headers.get("X-Agent-Token")
    if agent_token and agent_token.startswith("amu_") and "." in agent_token:
        try:
            agent_name = agent_token[4:].split(".", 1)[0]
            store = getattr(request.app.state, "identity_store", None)
            if store is not None:
                agent = await store.get_by_name(agent_name)
                if agent and not agent.revoked_at and verify_token(
                    agent_token, agent.token_hash
                ):
                    return RateLimitIdentity(
                        key=f"tier:agent:{agent.name}", limit="60/minute"
                    )
        except ValueError:
            pass
        # Token shaped correctly but failed verification — still "agent" tier by intent
        return RateLimitIdentity(
            key=f"tier:unverified:{get_remote_address(request)}", limit="10/minute"
        )

    api_key = request.headers.get("X-API-Key")
    if api_key:
        config = getattr(request.app.state, "config", None)
        if config and api_key == getattr(config, "api_key", None):
            key_hash = hashlib.md5(api_key.encode()).hexdigest()[:8]
            return RateLimitIdentity(
                key=f"tier:master:{key_hash}", limit="300/minute"
            )

    return RateLimitIdentity(
        key=f"tier:anon:{get_remote_address(request)}", limit="10/minute"
    )


class RateLimitIdentityMiddleware(BaseHTTPMiddleware):
    """Resolves rate-limit identity once per request, before slowapi runs.

    Stashes the result on `request.state.rate_limit_identity` so the sync
    key_func and tier resolver can read it without another DB call.
    """

    async def dispatch(self, request: Request, call_next):
        identity = await _resolve_identity(request)
        request.state.rate_limit_identity = identity
        return await call_next(request)


def agent_identity_key_func(request: Request) -> str:
    """Sync key_func — reads pre-resolved identity from request.state.

    The middleware always runs first; if it somehow didn't (e.g. an error
    before dispatch), we fall back to anonymous IP bucketing so we never
    return a coroutine or raise.
    """
    identity = getattr(request.state, "rate_limit_identity", None)
    if identity is not None:
        return identity.key
    return f"tier:anon:{get_remote_address(request)}"


def get_tier_limit(request: Request) -> str:
    """Sync tier-limit resolver — reads from request.state."""
    identity = getattr(request.state, "rate_limit_identity", None)
    if identity is not None:
        return identity.limit
    return "10/minute"


def get_limiter(redis_url: str | None = None) -> Limiter:
    """
    Initialize and return the slowapi Limiter.

    Uses get_tier_limit as the dynamic default so each identity tier
    (anonymous / agent / master) gets its own rate ceiling. Both key_func
    and get_tier_limit are synchronous — they read pre-resolved identity
    from request.state populated by RateLimitIdentityMiddleware.
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
    if request.headers.get("X-Agent-Token") or request.headers.get("X-API-Key"):
        return

    path = request.url.path
    if path not in ANON_ALLOWLIST:
        if request.method != "GET":
            raise HTTPException(
                status_code=403, detail="Anonymous write access denied"
            )
        if not any(path.startswith(p) for p in ANON_ALLOWLIST):
            raise HTTPException(
                status_code=403, detail="Anonymous access denied for this endpoint"
            )
