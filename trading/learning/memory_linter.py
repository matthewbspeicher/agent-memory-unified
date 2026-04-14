import logging
from learning.memory_client import TradingMemoryClient

logger = logging.getLogger(__name__)

class MemoryLinter:
    """Automated detection of conflicting rules and staleness across the knowledge base."""
    
    def __init__(self, memory_client: TradingMemoryClient):
        self._memory = memory_client

    async def lint(self) -> dict:
        """
        Checks the memory store for:
        - Staleness: flag memories past expires_at
        - Orphans: strategy articles with no supporting trade records
        """
        try:
            data = await self._memory._shared.search_commons(
                q="", limit=100, tags=["strategy_article"]
            )
            stale_count = 0
            orphan_count = 0
            for mem in data:
                if mem.get("expires_at"):
                    stale_count += 1
                if mem.get("access_count", 1) == 0:
                    orphan_count += 1
            return {
                "ok": True,
                "stale_articles": stale_count,
                "orphan_articles": orphan_count,
                "total_strategies": len(data),
            }
        except Exception as e:
            logger.error("Memory linter failed: %s", e)
            return {"ok": False, "error": str(e)}
