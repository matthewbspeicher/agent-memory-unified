"""TradingMemoryClient — namespace-aware wrapper around AsyncRemembrClient."""
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
        logger.warning("Private client does not support record_trade (SDK version mismatch?)")
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
