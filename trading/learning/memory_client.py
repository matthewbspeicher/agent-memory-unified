"""TradingMemoryClient — namespace-aware wrapper around AsyncRemembrClient with hybrid fallback."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TradingMemoryClient:
    """Routes memory writes to private agent namespace or shared market:observations.

    private_client: AsyncRemembrClient scoped to this agent's token.
    shared_client:  AsyncRemembrClient scoped to the shared market observations token.
    ttl_days:       Memories expire after this many days (applies to all writes).
    """

    def __init__(
        self,
        private_client: Any,
        shared_client: Any,
        ttl_days: int = 90,
    ) -> None:
        self._private = private_client
        self._shared = shared_client
        self._ttl = f"{ttl_days}d"

    async def store_private(self, content: str, tags: list[str] | None = None) -> dict:
        """Store a memory in the agent's private namespace with TTL."""
        return await self._private.store(
            value=content,
            visibility="private",
            tags=tags or [],
            ttl=self._ttl,
        )

    async def store_shared(self, content: str, tags: list[str] | None = None) -> dict:
        """Store a market observation in the shared commons namespace."""
        return await self._shared.store(
            value=content,
            visibility="public",
            tags=tags or [],
            ttl=self._ttl,
        )

    async def record_trade(self, **kwargs) -> dict:
        """Record a trade execution in the Remembr Trading Vertical."""
        if hasattr(self._private, "record_trade"):
            return await self._private.record_trade(**kwargs)
        logger.warning(
            "Private client does not support record_trade (SDK version mismatch?)"
        )
        return {}

    async def get_trading_stats(self, paper: bool = True) -> dict:
        """Retrieve aggregate performance stats from Remembr."""
        if hasattr(self._private, "get_trading_stats"):
            return await self._private.get_trading_stats(paper=paper)
        return {}

    async def search_both(self, query: str, top_k: int = 5) -> list[dict]:
        """Search private namespace and shared commons; combine results."""
        private_results: list[dict] = []
        shared_results: list[dict] = []
        try:
            private_results = await self._private.search(q=query, limit=top_k)
        except Exception as e:
            logger.warning("Private memory search failed: %s", e)
        try:
            shared_results = await self._shared.search_commons(q=query, limit=top_k)
        except Exception as e:
            logger.warning("Shared memory search failed: %s", e)
        # Combine: private first (agent-specific lessons take precedence)
        seen: set[str] = set()
        combined: list[dict] = []
        for r in private_results + shared_results:
            key = r.get("value", "")[:80]
            if key not in seen:
                seen.add(key)
                combined.append(r)
        return combined[:top_k]


class HybridTradingMemoryClient:
    """Hybrid memory client with remote primary and local fallback.

    Tries remembr.dev first, falls back to local store on failure.
    Useful when running without internet or when remembr.dev is down.
    """

    def __init__(
        self,
        remote_client: TradingMemoryClient,
        local_store: Any | None = None,
    ) -> None:
        self._remote = remote_client
        self._local = local_store
        self._use_local = False

    async def store_private(self, content: str, tags: list[str] | None = None) -> dict:
        """Store a memory - remote first, local fallback."""
        try:
            return await self._remote.store_private(content, tags)
        except Exception as e:
            logger.warning("Remote store_private failed: %s, trying local", e)
            if self._local:
                return await self._local.store(
                    value=content,
                    visibility="private",
                    tags=tags,
                )
            raise

    async def store_shared(self, content: str, tags: list[str] | None = None) -> dict:
        """Store a shared memory - remote first, local fallback."""
        try:
            return await self._remote.store_shared(content, tags)
        except Exception as e:
            logger.warning("Remote store_shared failed: %s, trying local", e)
            if self._local:
                return await self._local.store(
                    value=content,
                    visibility="public",
                    tags=tags,
                )
            raise

    async def search_both(self, query: str, top_k: int = 5) -> list[dict]:
        """Search memories - remote first, local fallback."""
        remote_results: list[dict] = []
        local_results: list[dict] = []

        # Try remote first
        try:
            remote_results = await self._remote.search_both(query, top_k)
        except Exception as e:
            logger.warning("Remote search_both failed: %s", e)

        # Try local as supplement/fallback
        if self._local:
            try:
                local_results = await self._local.search(query, limit=top_k)
            except Exception as e:
                logger.warning("Local search failed: %s", e)

        # Combine results (remote takes precedence)
        combined = remote_results.copy()
        seen = {r.get("value", "")[:80] for r in remote_results}
        for r in local_results:
            key = r.get("value", "")[:80]
            if key not in seen:
                combined.append(r)
                seen.add(key)

        return combined[:top_k]

    async def health_check(self) -> dict:
        """Check health of both backends."""
        remote_health = {"healthy": False}
        local_health = {"healthy": False}

        # Check remote
        try:
            # Simple check - try a search
            await self._remote.search_both("health", limit=1)
            remote_health = {"healthy": True, "backend": "remembr.dev"}
        except Exception as e:
            remote_health = {
                "healthy": False,
                "backend": "remembr.dev",
                "error": str(e),
            }

        # Check local
        if self._local:
            local_health = await self._local.health_check()
            if local_health.get("healthy"):
                local_health["backend"] = "local"

        # Overall health: remote is preferred, local is fallback
        return {
            "remote": remote_health,
            "local": local_health,
            "using": "local"
            if not remote_health.get("healthy") and local_health.get("healthy")
            else "remote",
        }
