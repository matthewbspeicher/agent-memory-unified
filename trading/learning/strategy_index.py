import logging
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
            data = await self._memory._shared.search_commons(
                q="", limit=100, tags=["strategy_article"]
            )
            index = []
            for mem in data:
                content = mem.get("value", "")
                summary = content[:150].replace("\n", " ") + "..."
                index.append({
                    "id": mem.get("id", mem.get("key")),
                    "tags": mem.get("tags", []),
                    "summary": summary,
                })
            return index
        except Exception as e:
            logger.error("Failed to generate memory index: %s", e)
            return []
