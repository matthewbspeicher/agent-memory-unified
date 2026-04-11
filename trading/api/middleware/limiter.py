import logging
import hashlib
from fastapi import Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
import os

logger = logging.getLogger(__name__)

# Allowlist for anonymous read-only access
ANON_ALLOWLIST = {
    "/engine/v1/health",
    "/engine/v1/health/live",
    "/engine/v1/health/ready",
    "/metrics",
    "/engine/v1/bittensor/kg/stats",
}

def agent_identity_key_func(request: Request) -> str:
    """
    Custom key function for rate limiting.
    Tiers:
    1. Verified Agent: X-Agent-Token present
    2. Master: X-API-Key present (and no X-Agent-Token)
    3. Anonymous: No auth headers
    """
    agent_token = request.headers.get("X-Agent-Token")
    if agent_token:
        return f"tier:agent:{agent_token}"
    
    api_key = request.headers.get("X-API-Key")
    if api_key:
        key_hash = hashlib.md5(api_key.encode()).hexdigest()[:8]
        return f"tier:master:{key_hash}"
    
    ip = get_remote_address(request)
    return f"tier:anon:{ip}"

def get_tier_limit(request: Request) -> str:
    """Return the limit string based on the identity tier."""
    agent_token = request.headers.get("X-Agent-Token")
    if agent_token:
        return "60/minute"
    
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return "300/minute"
    
    # Anonymous Tier
    path = request.url.path
    # Basic check: if not in allowlist, anon gets even stricter limit or rejected
    # but the middleware will handle the 'limit' part. 
    # We enforce the allowlist separately in a dependency or middleware.
    return "10/minute"

def get_limiter(redis_url: str | None = None) -> Limiter:
    """
    Initialize and return the slowapi Limiter.
    """
    storage_uri = redis_url if redis_url else "memory://"
    if storage_uri.startswith("redis://") and not storage_uri.startswith("async+redis://"):
        storage_uri = storage_uri.replace("redis://", "async+redis://")

    return Limiter(
        key_func=agent_identity_key_func,
        storage_uri=storage_uri,
        strategy="moving-window",
        default_limits=["10/minute"], # Default strictly for anon
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
             raise HTTPException(status_code=403, detail="Anonymous access denied for this endpoint")
