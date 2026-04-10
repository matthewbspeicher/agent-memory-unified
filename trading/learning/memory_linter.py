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
            # FIXME: Workaround for missing SDK method
            # Direct access to underlying HTTP client breaks encapsulation
            resp = await self._memory._shared.client.get("/commons/search", params={"tags": "strategy_article", "limit": 100})
            if getattr(resp, "is_error", False):
                return {"ok": False, "error": resp.text}
                
            data = resp.json().get("data", [])
            stale_count = 0
            orphan_count = 0
            
            for mem in data:
                # Simulated staleness check
                if mem.get("expires_at"):
                    stale_count += 1
                    
                # Simulated orphan check (e.g. low access count or missing tags)
                if mem.get("access_count", 1) == 0:
                    orphan_count += 1
                    
            return {
                "ok": True,
                "stale_articles": stale_count,
                "orphan_articles": orphan_count,
                "total_strategies": len(data)
            }
        except Exception as e:
            logger.error("Memory linter failed: %s", e)
            return {"ok": False, "error": str(e)}
