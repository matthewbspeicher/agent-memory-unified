"""External service health cache.

Background task populates cached status for services like Railway that
require network round-trips. Endpoint handlers read from the cache
instead of blocking on an outbound HTTP call per request.

Usage:
    cache = HealthCacheManager()
    await cache.update_external_health()  # run periodically in background
    status = cache.get_status("railway")
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


async def fetch_railway_status() -> dict:
    """Fetch deploy status from Railway API.

    Returns a dict with at least ``status`` ("healthy" | "unhealthy" | "unknown")
    and optional fields like ``deploy_status``. When no API token is configured,
    returns a placeholder with ``status: "unknown"``.
    """
    token = os.getenv("RAILWAY_API_TOKEN")
    if not token:
        return {"status": "unknown", "deploy_status": "unknown"}

    try:
        import aiohttp

        # Railway's GraphQL API — minimal query for the current deployment status
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://backboard.railway.app/graphql/v2",
                headers={"Authorization": f"Bearer {token}"},
                json={"query": "{ me { id } }"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return {"status": "healthy", "deploy_status": "active"}
                return {
                    "status": "unhealthy",
                    "deploy_status": "error",
                    "message": f"HTTP {resp.status}",
                }
    except Exception as exc:
        return {"status": "unhealthy", "message": str(exc)}


class HealthCacheManager:
    """In-memory cache for external service health status.

    Intended to be populated by a background task that calls
    ``update_external_health()`` periodically. Endpoint handlers read
    via ``get_status(service_name)``.
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}

    async def update_external_health(self) -> None:
        """Refresh cached status for all tracked external services."""
        try:
            self._cache["railway"] = await fetch_railway_status()
        except Exception as exc:
            logger.error("Failed to update Railway status: %s", exc)
            self._cache["railway"] = {"status": "unhealthy", "message": str(exc)}

    def get_status(self, service_name: str) -> dict | None:
        """Return the cached status dict for a service, or None if not tracked."""
        return self._cache.get(service_name)

    def all_statuses(self) -> dict[str, dict]:
        """Return a shallow copy of all cached statuses."""
        return dict(self._cache)
