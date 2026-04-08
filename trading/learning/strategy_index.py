import logging
from typing import Any
from learning.memory_client import TradingMemoryClient

logger = logging.getLogger(__name__)

class MemoryIndexService:
    """Service to generate a compressed catalog of strategy articles for index-guided retrieval."""
    
    def __init__(self, memory_client: TradingMemoryClient):
        self._memory = memory_client

    async def get_compressed_index(self) -> list[dict]:
        """
        Fetches all strategy articles and daily summaries and returns a compressed
        catalog for the LLM to read before selecting specific documents.
        """
        try:
            # FIXME: Workaround for missing SDK method (e.g. `await self._memory._shared.get_all(tags=["strategy_article"])`)
            # Direct access to underlying HTTP client breaks encapsulation
            resp = await self._memory._shared.client.get("/commons/search", params={"tags": "strategy_article", "limit": 100})
            if getattr(resp, "is_error", False):
                logger.warning("Failed to fetch strategy articles for index: %s", resp.text)
                return []
                
            data = resp.json().get("data", [])
            
            index = []
            for mem in data:
                content = mem.get("value", "")
                summary = content[:150].replace("\n", " ") + "..." # 1-line summary
                index.append({
                    "id": mem.get("id", mem.get("key")),
                    "tags": mem.get("tags", []),
                    "summary": summary
                })
            return index
        except Exception as e:
            logger.error("Failed to generate memory index: %s", e)
            return []
