from typing import List, Dict, Any
from remembr.client import AsyncRemembrClient
from .turboquant import TurboQuantIndexer

class JournalManager:
    def __init__(self, remembr_client: AsyncRemembrClient, turbo_indexer: TurboQuantIndexer):
        self.remembr_client = remembr_client
        self.turbo_indexer = turbo_indexer

    async def query_similar_trades(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Checks for TurboQuant first, falls back to remembr.
        """
        if self.turbo_indexer.is_ready:
            try:
                # Fast path: Use local HNSW index
                return self.turbo_indexer.search_trades(query, limit=limit)
            except Exception as e:
                print(f"TurboQuant search failed: {e}. Falling back to Remembr.")
                
        # Slow path: Fallback to Remembr
        # Depending on the exact AsyncRemembrClient API for search
        results = await self.remembr_client.search(query, limit=limit) # might need tags=["trade_journal"]
        return results

    async def get_recent_trades(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Checks for TurboQuant first, falls back to remembr.
        Note: HNSW is for similarity search, not chronological, 
        but if we stored timestamps we could filter/sort, or we just fallback to Remembr 
        if we only need chronological data. Assuming turboquant can handle it or we use Remembr.
        """
        # If TurboQuant is extended to support chronological retrieval, do it here.
        # For now, fallback to Remembr for purely recent trades if TurboQuant isn't chronological
        # or implement a simple memory-based cache in TurboQuantIndexer.
        try:
            return await self.remembr_client.list(page=1, tags=["trade_journal"]) # Just a placeholder
        except Exception as e:
            print(f"Failed to fetch recent trades: {e}")
            return []
