from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

# sentence_transformers / torch are loaded lazily in start() to avoid
# a fatal libomp duplicate-library abort that occurs when torch loads
# alongside other OpenMP-linked C extensions (e.g. numpy).  The module-level
# import was triggering torch init at collection time, crashing pytest.
SentenceTransformer = None  # type: ignore[assignment,misc]


def _load_sentence_transformer_class():
    """Import SentenceTransformer lazily to avoid torch init at import time."""
    global SentenceTransformer
    if SentenceTransformer is not None:
        return SentenceTransformer
    try:
        from sentence_transformers import SentenceTransformer as _ST

        SentenceTransformer = _ST
    except ImportError:
        SentenceTransformer = None  # type: ignore[assignment]
    return SentenceTransformer


if TYPE_CHECKING:
    from data.events import EventBus
    from remembr.client import AsyncRemembrClient

logger = logging.getLogger(__name__)

TOMBSTONE_STATUSES = frozenset({"cancelled", "rejected"})


@dataclass
class SearchResult:
    memory_id: str
    score: float | None
    content: str
    metadata: dict


class JournalIndexer:
    """
    Local HNSW vector index for fast journal trade lookups.
    Thread-safe implementation with asyncio.Lock protecting mutations.
    """

    def __init__(
        self,
        event_bus: EventBus,
        remembr_client: AsyncRemembrClient,
        gpu_enabled: bool = False,
        model_name: str = "all-MiniLM-L6-v2",
        index_path: str = "data/journal_index",
        space: str = "cosine",
        ef_construction: int = 200,
        m: int = 16,
        ef_search: int = 50,
        max_elements: int = 100_000,
        batch_size: int = 128,
    ) -> None:
        self._event_bus = event_bus
        self._remembr_client = remembr_client
        self._model_name = model_name
        self._index_path = index_path
        self._space = space
        self._ef_construction = ef_construction
        self._m = m
        self._ef_search = ef_search
        self._max_elements = max_elements
        self._batch_size = batch_size
        self._gpu_enabled = gpu_enabled

        # Index state
        self._index = None  # hnswlib.Index, initialized in start()
        self._model = None  # SentenceTransformer, loaded in start()
        self._dim: int = 384  # MiniLM embedding dimension

        # Caches
        self._metadata: dict[str, dict] = {}
        self._content: dict[str, str] = {}
        self._symbol_index: dict[str, list[str]] = {}
        self._id_map: dict[str, int] = {}
        self._label_to_id: dict[int, str] = {}
        self._next_label: int = 0
        self._tombstone_count: int = 0
        self._meta_size_bytes: int = 0

        # Lifecycle
        self.is_ready: bool = False
        self._event_buffer: list[dict] = []
        self._subscriber_task: asyncio.Task | None = None
        self._rehydrate_task: asyncio.Task | None = None
        self._lock: threading.Lock = threading.Lock()

    @property
    def entry_count(self) -> int:
        return len(self._metadata)

    @property
    def memory_mb(self) -> float:
        embedding_bytes = self._next_label * self._dim * 4
        return (embedding_bytes + self._meta_size_bytes) / (1024 * 1024)

    async def start(self) -> None:
        """Non-blocking startup: loads model, inits index, starts background tasks."""
        ST = _load_sentence_transformer_class()
        if ST is None:
            logger.error(
                "sentence-transformers not installed — JournalIndexer disabled"
            )
            return

        def load_model():
            device = "cpu"
            try:
                import torch

                if self._gpu_enabled and torch.cuda.is_available():
                    device = "cuda"
            except ImportError:
                pass
            logger.info("JournalIndexer: loading SentenceTransformer on %s", device)
            return ST(self._model_name, device=device)

        self._model = await asyncio.to_thread(load_model)
        self._dim = self._model.get_sentence_embedding_dimension()

        import hnswlib

        loaded = await self.load()
        if not loaded:
            self._index = hnswlib.Index(space=self._space, dim=self._dim)
            self._index.init_index(
                max_elements=self._max_elements,
                ef_construction=self._ef_construction,
                M=self._m,
            )
            self._index.set_ef(self._ef_search)

        self._subscriber_task = asyncio.create_task(self._run_subscriber())
        self._rehydrate_task = asyncio.create_task(self._rehydrate())

        logger.info("JournalIndexer: started (background rehydration in progress)")

    async def stop(self) -> None:
        """Graceful shutdown: cancel tasks, persist state."""
        if self._subscriber_task and not self._subscriber_task.done():
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError:
                pass

        if self._rehydrate_task and not self._rehydrate_task.done():
            self._rehydrate_task.cancel()
            try:
                await self._rehydrate_task
            except asyncio.CancelledError:
                pass

        if self._next_label > 0:
            await self.persist()
        logger.info("JournalIndexer: stopped")

    async def _rehydrate(self) -> None:
        """Fetch all trade journal entries from remembr and index them in batches."""
        page = 1
        batch_mids: list[str] = []
        batch_contents: list[str] = []
        batch_metadatas: list[dict] = []

        try:
            while True:
                resp = await self._remembr_client.list(
                    page=page, tags=["trade_journal"]
                )
                entries = resp.get("data", [])
                if not entries:
                    break

                for entry in entries:
                    mid = entry.get("id")
                    if not mid or mid in self._metadata:
                        continue

                    batch_mids.append(mid)
                    batch_contents.append(entry.get("value", ""))
                    batch_metadatas.append(entry.get("metadata", {}))

                    if len(batch_mids) >= self._batch_size:
                        await self._add_entries_batch_async(
                            batch_mids, batch_contents, batch_metadatas
                        )
                        batch_mids, batch_contents, batch_metadatas = [], [], []

                total_pages = resp.get("total_pages", 1)
                if page >= total_pages:
                    break
                page += 1

            # Flush remaining
            if batch_mids:
                await self._add_entries_batch_async(
                    batch_mids, batch_contents, batch_metadatas
                )

        except Exception:
            logger.exception(
                "JournalIndexer: rehydration failed at page %d — continuing with partial data",
                page,
            )

        # Drain event buffer atomically
        buffer, self._event_buffer = self._event_buffer, []
        for event in buffer:
            data = event.get("data", {})
            topic = event.get("topic", "")
            if topic == "journal.entry_added":
                await self._handle_entry_added(data)
            elif topic == "journal.entry_updated":
                await self._handle_entry_updated(data)

        self.is_ready = True

        if self._next_label > 0:
            await self.persist()

        logger.info(
            "JournalIndexer: rehydration complete — %d entries indexed",
            self._next_label,
        )

    async def rebuild(self) -> None:
        """Nuke local state and rehydrate from remembr."""
        with self._lock:
            self.is_ready = False
            self._metadata.clear()
            self._content.clear()
            self._symbol_index.clear()
            self._id_map.clear()
            self._label_to_id.clear()
            self._next_label = 0
            self._tombstone_count = 0
            self._meta_size_bytes = 0

            import hnswlib

            self._index = hnswlib.Index(space=self._space, dim=self._dim)
            self._index.init_index(
                max_elements=self._max_elements,
                ef_construction=self._ef_construction,
                M=self._m,
            )
            self._index.set_ef(self._ef_search)

        # Delete stale cache files
        for suffix in (".hnsw", ".meta.json"):
            path = f"{self._index_path}{suffix}"
            if os.path.exists(path):
                os.remove(path)

        await self._rehydrate()

    async def _add_entry_async(
        self, memory_id: str, content: str, metadata: dict
    ) -> None:
        """Async wrapper around single entry add."""
        await self._add_entries_batch_async([memory_id], [content], [metadata])

    async def _add_entries_batch_async(
        self, memory_ids: list[str], contents: list[str], metadatas: list[dict]
    ) -> None:
        """Async wrapper around vectorized batch entry add with lock safety."""
        await asyncio.to_thread(
            self._add_entries_batch_sync, memory_ids, contents, metadatas
        )

    def _add_entries_batch_sync(
        self, memory_ids: list[str], contents: list[str], metadatas: list[dict]
    ) -> None:
        """Synchronous vectorized batch add: embed batch, insert into HNSW, update caches."""
        with self._lock:
            valid_indices = [
                i for i, mid in enumerate(memory_ids) if mid not in self._id_map
            ]
            if not valid_indices:
                return

            batch_mids = [memory_ids[i] for i in valid_indices]
            batch_contents = [contents[i] for i in valid_indices]
            batch_metadatas = [metadatas[i] for i in valid_indices]
            num_new = len(batch_mids)

            # Auto-resize at 90% capacity
            if self._next_label + num_new >= int(self._max_elements * 0.9):
                new_cap = max(
                    int(self._max_elements * 1.5), self._next_label + num_new + 1000
                )
                self._index.resize_index(new_cap)
                self._max_elements = new_cap
                logger.info("JournalIndexer: resized index to %d", new_cap)

            # Vectorized embedding generation
            vecs = self._model.encode(batch_contents)
            if vecs.ndim == 1:
                vecs = vecs.reshape(1, -1)

            labels = np.arange(self._next_label, self._next_label + num_new)
            self._index.add_items(vecs, labels)

            for i, mid in enumerate(batch_mids):
                label = int(labels[i])
                metadata = batch_metadatas[i]
                content = batch_contents[i]

                self._id_map[mid] = label
                self._label_to_id[label] = mid
                self._metadata[mid] = metadata
                self._content[mid] = content
                self._meta_size_bytes += len(json.dumps(metadata, default=str).encode())

                symbol = metadata.get("decision", {}).get("symbol")
                if symbol:
                    self._symbol_index.setdefault(symbol, []).append(mid)

            self._next_label += num_new

    def _add_entry_sync(self, memory_id: str, content: str, metadata: dict) -> None:
        """Synchronous: legacy wrapper for single entry add."""
        self._add_entries_batch_sync([memory_id], [content], [metadata])

    def _update_entry_sync(self, memory_id: str, content: str, metadata: dict) -> None:
        """Synchronous: Re-embed and replace an existing entry (tombstoning the old label)."""
        with self._lock:
            if memory_id not in self._id_map:
                return

            old_label = self._id_map[memory_id]

            # Tombstone old entry in index if supported
            if hasattr(self._index, "mark_deleted"):
                try:
                    self._index.mark_deleted(old_label)
                except Exception as e:
                    logger.warning(
                        "JournalIndexer: failed to mark label %d as deleted: %s",
                        old_label,
                        e,
                    )

            # Auto-resize if needed
            if self._next_label + 1 >= int(self._max_elements * 0.9):
                new_cap = int(self._max_elements * 1.5)
                self._index.resize_index(new_cap)
                self._max_elements = new_cap
                logger.info("JournalIndexer: resized index to %d", new_cap)

            # Generate new embedding
            vec = self._model.encode([content])
            if vec.ndim == 1:
                vec = vec.reshape(1, -1)

            new_label = self._next_label
            self._index.add_items(vec, [new_label])

            # Update mappings
            self._id_map[memory_id] = new_label
            self._label_to_id[new_label] = memory_id
            if old_label in self._label_to_id:
                del self._label_to_id[old_label]

            self._content[memory_id] = content
            self._metadata[memory_id] = metadata

            self._next_label += 1
            self._tombstone_count += 1

            logger.debug(
                "JournalIndexer: re-embedded memory_id %s (label %d -> %d)",
                memory_id,
                old_label,
                new_label,
            )

    def _is_tombstoned(self, memory_id: str) -> bool:
        status = self._metadata.get(memory_id, {}).get("status", "")
        return status in TOMBSTONE_STATUSES

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Synchronous — call via asyncio.to_thread from async callers."""
        if self._index is None or self._next_label == 0:
            return []

        vec = self._model.encode(query)
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)

        k = min(limit * 2, self._next_label - self._tombstone_count)
        if k <= 0:
            return []
        labels, distances = self._index.knn_query(vec, k=k)

        results: list[SearchResult] = []
        for label, dist in zip(labels[0], distances[0]):
            mid = self._label_to_id.get(int(label))
            if mid is None or self._is_tombstoned(mid):
                continue
            score = max(0.0, 1.0 - float(dist))
            results.append(
                SearchResult(
                    memory_id=mid,
                    score=score,
                    content=self._content.get(mid, ""),
                    metadata=self._metadata.get(mid, {}),
                )
            )
            if len(results) >= limit:
                break

        return results

    async def persist(self) -> None:
        """Atomic write: save HNSW index + metadata to disk."""
        await asyncio.to_thread(self._persist_sync)

    def _persist_sync(self) -> None:
        """Synchronous persistence logic."""
        with self._lock:
            if self._index is None or self._next_label == 0:
                return

            os.makedirs(os.path.dirname(self._index_path) or ".", exist_ok=True)

            hnsw_path = f"{self._index_path}.hnsw"
            meta_path = f"{self._index_path}.meta.json"

            hnsw_tmp = f"{hnsw_path}.tmp"
            self._index.save_index(hnsw_tmp)
            os.replace(hnsw_tmp, hnsw_path)

            meta_tmp = f"{meta_path}.tmp"
            state = {
                "metadata": self._metadata,
                "content": self._content,
                "symbol_index": self._symbol_index,
                "id_map": self._id_map,
                "label_to_id": {str(k): v for k, v in self._label_to_id.items()},
                "next_label": self._next_label,
                "tombstone_count": self._tombstone_count,
                "max_elements": self._max_elements,
            }
            with open(meta_tmp, "w") as f:
                json.dump(state, f)
            os.replace(meta_tmp, meta_path)

            logger.info(
                "JournalIndexer: persisted %d entries to %s",
                self._next_label,
                self._index_path,
            )

    async def load(self) -> bool:
        """Load HNSW index + metadata from disk. Returns True on success."""
        return await asyncio.to_thread(self._load_sync)

    def _load_sync(self) -> bool:
        """Synchronous load logic."""
        hnsw_path = f"{self._index_path}.hnsw"
        meta_path = f"{self._index_path}.meta.json"

        if not os.path.exists(hnsw_path) or not os.path.exists(meta_path):
            return False

        try:
            import hnswlib

            with open(meta_path, "r") as f:
                state = json.load(f)

            with self._lock:
                self._metadata = state["metadata"]
                self._content = state["content"]
                self._symbol_index = state["symbol_index"]
                self._id_map = state["id_map"]
                self._label_to_id = {int(k): v for k, v in state["label_to_id"].items()}
                self._next_label = state["next_label"]
                self._tombstone_count = state.get("tombstone_count", 0)
                self._max_elements = state.get("max_elements", self._max_elements)

                self._index = hnswlib.Index(space=self._space, dim=self._dim)
                self._index.load_index(hnsw_path, max_elements=self._max_elements)
                self._index.set_ef(self._ef_search)

                # Recompute incremental metadata size counter
                self._meta_size_bytes = (
                    len(json.dumps(self._metadata, default=str).encode())
                    if self._metadata
                    else 0
                )

            logger.info(
                "JournalIndexer: loaded %d entries from disk cache", self._next_label
            )
            return True

        except Exception as e:
            logger.warning("JournalIndexer: failed to load disk cache: %s", e)
            with self._lock:
                self._metadata = {}
                self._content = {}
                self._symbol_index = {}
                self._id_map = {}
                self._label_to_id = {}
                self._next_label = 0
                self._tombstone_count = 0
            return False

    def get_by_symbol(self, symbol: str, limit: int = 20) -> list[SearchResult]:
        """Synchronous — pure dict ops, call directly (no to_thread needed)."""
        memory_ids = self._symbol_index.get(symbol, [])
        results: list[SearchResult] = []
        for mid in memory_ids:
            if self._is_tombstoned(mid):
                continue
            results.append(
                SearchResult(
                    memory_id=mid,
                    score=None,
                    content=self._content.get(mid, ""),
                    metadata=self._metadata.get(mid, {}),
                )
            )

        def _ts_key(r: SearchResult) -> str:
            return r.metadata.get("decision", {}).get("timestamp", "")

        results.sort(key=_ts_key, reverse=True)
        return results[:limit]

    async def _handle_entry_added(self, payload: dict) -> None:
        memory_id = payload.get("memory_id")
        content = payload.get("content", "")
        metadata = payload.get("metadata", {})

        if not memory_id or not content:
            return

        await self._add_entry_async(memory_id, content, metadata)

    async def _handle_entry_updated(self, payload: dict) -> None:
        memory_id = payload.get("memory_id")
        content = payload.get("content")
        metadata = payload.get("metadata")

        if not memory_id or memory_id not in self._metadata:
            return

        # Check if content changed. If so, re-embed.
        if content is not None and content != self._content.get(memory_id):
            await asyncio.to_thread(
                self._update_entry_sync, memory_id, content, metadata
            )
        else:

            def _update_meta():
                with self._lock:
                    self._metadata[memory_id] = metadata

            await asyncio.to_thread(_update_meta)

    async def _run_subscriber(self) -> None:
        try:
            async for event in self._event_bus.subscribe():
                topic = event.get("topic", "")
                if not topic.startswith("journal."):
                    continue

                data = event.get("data", {})

                if not self.is_ready:
                    self._event_buffer.append(event)
                    continue

                if topic == "journal.entry_added":
                    await self._handle_entry_added(data)
                elif topic == "journal.entry_updated":
                    await self._handle_entry_updated(data)
        except asyncio.CancelledError:
            logger.info("JournalIndexer: subscriber cancelled")
        except Exception:
            logger.exception("JournalIndexer: subscriber error")
