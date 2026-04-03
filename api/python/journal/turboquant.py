import os
import asyncio
import logging
from typing import List, Dict, Any, Optional
from remembr.client import AsyncRemembrClient
from remembr.turbo import TurboQuantIndex

logger = logging.getLogger("TurboQuantIndexer")

# Event names — used by both EventBus subscribers and emitters
EVENT_TRADE_CREATED = "trade.created"
EVENT_TRADE_UPDATED = "trade.updated"
EVENT_TRADE_DELETED = "trade.deleted"


class TurboQuantIndexer:
    """
    Manages a local HNSW vector index over trade journal entries.
    
    Lifecycle:
        1. initialize() — loads from disk or rehydrates from remembr
        2. subscribe(event_bus) — wires handlers to the event bus
        3. search_trades() — fast-path local search with remote fallback
        4. shutdown() — persists final state & cancels background tasks
    """

    def __init__(
        self,
        client: AsyncRemembrClient,
        persist_path: str = "./data/turboquant",
        persist_interval_seconds: int = 30,
    ):
        self.client = client
        self.persist_path = persist_path
        self.persist_interval = persist_interval_seconds
        self.index = TurboQuantIndex()
        self.is_ready = False
        self._persist_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """
        Handles startup rehydration from remembr.
        Loads from disk if available, otherwise fetches all from remembr and builds index.
        """
        if os.path.exists(os.path.join(self.persist_path, "turboquant.bin")):
            self.index.load(self.persist_path)
            self.is_ready = True
            logger.info(f"Loaded TurboQuantIndex from disk ({len(self.index._id_to_internal)} entries)")
            return

        logger.info("Rehydrating TurboQuantIndex from Remembr...")
        total = 0
        page = 1
        while True:
            try:
                results = await self.client.list(page=page, tags=["trade_journal"])
                if not results:
                    break
            except (AttributeError, Exception) as e:
                logger.warning(f"Rehydration page {page} failed: {e}")
                break

            memory_ids = []
            texts = []
            metadatas = []

            for entry in results:
                memory_ids.append(entry.get("id") or entry.get("_id"))
                texts.append(entry.get("value", ""))
                metadatas.append(self._extract_metadata(entry))

            self.index.add_batch(memory_ids=memory_ids, texts=texts, metadatas=metadatas)
            total += len(results)

            if len(results) < 50:
                break
            page += 1

        self.index.persist(self.persist_path)
        self.is_ready = True
        logger.info(f"Rehydrated TurboQuantIndex with {total} entries")

    def subscribe(self, event_bus):
        """Wire all trade lifecycle handlers to an EventBus instance."""
        event_bus.subscribe(EVENT_TRADE_CREATED, self.handle_new_trade)
        event_bus.subscribe(EVENT_TRADE_UPDATED, self.handle_update_trade)
        event_bus.subscribe(EVENT_TRADE_DELETED, self.handle_delete_trade)
        logger.info("TurboQuantIndexer subscribed to trade events")

    def start_persistence_loop(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start the periodic background persistence task."""
        target_loop = loop or asyncio.get_event_loop()
        self._persist_task = target_loop.create_task(self._periodic_persist())
        logger.info(f"Started persistence loop (interval={self.persist_interval}s)")

    async def shutdown(self):
        """Persist final state and cancel background tasks."""
        if self._persist_task and not self._persist_task.done():
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass

        if self.index.is_dirty:
            self.index.persist(self.persist_path)
            logger.info("Final persistence on shutdown complete")

    # --- Event Handlers ---

    async def handle_new_trade(self, event: Dict[str, Any]):
        """Handle new trade journal entries."""
        entry = event.get("data", {})
        memory_id = entry.get("id") or entry.get("_id")
        if not memory_id:
            logger.warning("Received trade.created event without an ID, skipping")
            return

        text = entry.get("value", "")
        metadata = self._extract_metadata(entry)
        self.index.add(memory_id=memory_id, text=text, metadata=metadata)
        logger.debug(f"Indexed new trade {memory_id}")

    async def handle_update_trade(self, event: Dict[str, Any]):
        """Handle updates (PnL, exit reasoning, status changes) to trade journal entries."""
        entry = event.get("data", {})
        memory_id = entry.get("id") or entry.get("_id")
        if not memory_id:
            logger.warning("Received trade.updated event without an ID, skipping")
            return

        text = entry.get("value", "")
        metadata = self._extract_metadata(entry)
        self.index.update(memory_id=memory_id, text=text, metadata=metadata)
        logger.debug(f"Updated trade {memory_id} in index")

    async def handle_delete_trade(self, event: Dict[str, Any]):
        """Remove a trade journal entry from the local index."""
        memory_id = event.get("data", {}).get("id") or event.get("data", {}).get("_id")
        if memory_id:
            self.index.delete(memory_id)
            logger.debug(f"Deleted trade {memory_id} from index")

    # --- Search ---

    async def search_trades(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fast-path local search with automatic fallback to remote remembr.search().
        """
        if not self.is_ready:
            logger.warning("Index not ready, falling back to remote search")
            return await self._remote_search(query, limit)

        try:
            return self.index.search(query, k=limit)
        except Exception as e:
            logger.error(f"Local search failed, falling back to remote: {e}")
            return await self._remote_search(query, limit)

    async def _remote_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Fallback to the remote remembr API for search."""
        try:
            results = await self.client.search(query=query, limit=limit, tags=["trade_journal"])
            return results if results else []
        except Exception as e:
            logger.error(f"Remote search also failed: {e}")
            return []

    # --- Internal ---

    async def _periodic_persist(self):
        """Background task that persists the index if dirty, on a timer."""
        while True:
            try:
                await asyncio.sleep(self.persist_interval)
                if self.index.is_dirty:
                    self.index.persist(self.persist_path)
                    logger.debug("Periodic persistence complete")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Periodic persistence failed: {e}", exc_info=True)

    @staticmethod
    def _extract_metadata(entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardized metadata from a trade journal entry."""
        meta = entry.get("metadata", {})
        return {
            "realized_pnl": meta.get("realized_pnl"),
            "status": meta.get("status"),
            "direction": meta.get("decision", {}).get("direction"),
            "ticker": meta.get("ticker"),
            "strategy": meta.get("strategy"),
        }
