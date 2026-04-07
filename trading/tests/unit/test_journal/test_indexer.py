import pytest
from unittest.mock import MagicMock, AsyncMock
import numpy as np
from journal.indexer import JournalIndexer, SearchResult


def test_search_result_with_score():
    r = SearchResult(
        memory_id="abc", score=0.95, content="trade text", metadata={"status": "open"}
    )
    assert r.memory_id == "abc"
    assert r.score == 0.95
    assert r.content == "trade text"
    assert r.metadata["status"] == "open"


def test_search_result_none_score():
    r = SearchResult(memory_id="abc", score=None, content="trade text", metadata={})
    assert r.score is None


@pytest.fixture
def mock_model():
    model = MagicMock()
    model.encode.return_value = np.random.randn(384).astype(np.float32)
    return model


@pytest.fixture
def indexer(mock_model):
    event_bus = MagicMock()
    remembr_client = AsyncMock()
    idx = JournalIndexer(
        event_bus=event_bus,
        remembr_client=remembr_client,
        index_path="/tmp/test_journal_index",
        max_elements=100,
    )
    idx._model = mock_model
    import hnswlib

    idx._index = hnswlib.Index(space="cosine", dim=384)
    idx._index.init_index(max_elements=100, ef_construction=200, M=16)
    idx._index.set_ef(50)
    idx.is_ready = True
    return idx


def test_add_entry_sync_and_search(indexer, mock_model):
    entry_vec = np.ones(384, dtype=np.float32)
    entry_vec /= np.linalg.norm(entry_vec)
    mock_model.encode.return_value = entry_vec

    indexer._add_entry_sync(
        memory_id="mem-1",
        content="Trade AAPL BUY confidence 0.9",
        metadata={
            "decision": {
                "symbol": "AAPL",
                "direction": "BUY",
                "timestamp": "2026-04-01T00:00:00+00:00",
            },
            "status": "open",
        },
    )

    assert indexer.entry_count == 1
    assert "mem-1" in indexer._metadata
    assert "AAPL" in indexer._symbol_index
    assert "mem-1" in indexer._symbol_index["AAPL"]

    results = indexer.search("Trade AAPL BUY", limit=5)
    assert len(results) == 1
    assert results[0].memory_id == "mem-1"
    assert results[0].score is not None
    assert results[0].score > 0


def test_get_by_symbol(indexer, mock_model):
    vec = np.random.randn(384).astype(np.float32)
    mock_model.encode.return_value = vec

    indexer._add_entry_sync(
        "mem-1",
        "Trade AAPL BUY",
        {
            "decision": {
                "symbol": "AAPL",
                "direction": "BUY",
                "timestamp": "2026-04-01T00:00:00+00:00",
            },
            "status": "closed",
            "realized_pnl": -10.0,
        },
    )
    indexer._add_entry_sync(
        "mem-2",
        "Trade TSLA SELL",
        {
            "decision": {
                "symbol": "TSLA",
                "direction": "SELL",
                "timestamp": "2026-04-01T01:00:00+00:00",
            },
            "status": "open",
        },
    )
    indexer._add_entry_sync(
        "mem-3",
        "Trade AAPL SELL",
        {
            "decision": {
                "symbol": "AAPL",
                "direction": "SELL",
                "timestamp": "2026-04-01T02:00:00+00:00",
            },
            "status": "open",
        },
    )

    results = indexer.get_by_symbol("AAPL", limit=10)
    assert len(results) == 2
    assert all(r.score is None for r in results)
    assert results[0].memory_id == "mem-3"
    assert results[1].memory_id == "mem-1"


def test_tombstone_filtering(indexer, mock_model):
    vec = np.random.randn(384).astype(np.float32)
    mock_model.encode.return_value = vec

    indexer._add_entry_sync(
        "mem-1",
        "Trade AAPL BUY",
        {
            "decision": {
                "symbol": "AAPL",
                "direction": "BUY",
                "timestamp": "2026-04-01T00:00:00+00:00",
            },
            "status": "open",
        },
    )
    indexer._add_entry_sync(
        "mem-2",
        "Trade AAPL SELL",
        {
            "decision": {
                "symbol": "AAPL",
                "direction": "SELL",
                "timestamp": "2026-04-01T01:00:00+00:00",
            },
            "status": "cancelled",
        },
    )

    results = indexer.get_by_symbol("AAPL", limit=10)
    assert len(results) == 1
    assert results[0].memory_id == "mem-1"

    search_results = indexer.search("Trade AAPL", limit=10)
    assert all(r.memory_id != "mem-2" for r in search_results)


def test_auto_resize(mock_model):
    event_bus = MagicMock()
    remembr_client = AsyncMock()
    idx = JournalIndexer(
        event_bus=event_bus,
        remembr_client=remembr_client,
        index_path="/tmp/test_resize",
        max_elements=10,
    )
    idx._model = mock_model
    import hnswlib

    idx._index = hnswlib.Index(space="cosine", dim=384)
    idx._index.init_index(max_elements=10, ef_construction=200, M=16)
    idx._index.set_ef(50)
    idx.is_ready = True

    vec = np.random.randn(384).astype(np.float32)
    mock_model.encode.return_value = vec

    for i in range(10):
        idx._add_entry_sync(
            f"mem-{i}",
            f"Trade {i}",
            {
                "decision": {
                    "symbol": "TEST",
                    "direction": "BUY",
                    "timestamp": f"2026-04-01T{i:02d}:00:00+00:00",
                },
                "status": "open",
            },
        )

    assert idx._max_elements > 10
    assert idx.entry_count == 10


def test_add_entry_sync_skips_duplicate(indexer, mock_model):
    vec = np.random.randn(384).astype(np.float32)
    mock_model.encode.return_value = vec

    indexer._add_entry_sync(
        "mem-1",
        "Trade AAPL BUY",
        {
            "decision": {
                "symbol": "AAPL",
                "direction": "BUY",
                "timestamp": "2026-04-01T00:00:00+00:00",
            },
            "status": "open",
        },
    )
    indexer._add_entry_sync(
        "mem-1",
        "Trade AAPL BUY DUPLICATE",
        {
            "decision": {
                "symbol": "AAPL",
                "direction": "BUY",
                "timestamp": "2026-04-01T00:00:00+00:00",
            },
            "status": "open",
        },
    )

    assert indexer.entry_count == 1
    assert indexer._content["mem-1"] == "Trade AAPL BUY"


def test_search_empty_index(indexer, mock_model):
    results = indexer.search("anything", limit=5)
    assert results == []


import tempfile
import os


@pytest.mark.asyncio
async def test_persist_and_load(mock_model):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_idx")

        event_bus = MagicMock()
        remembr_client = AsyncMock()

        idx1 = JournalIndexer(
            event_bus=event_bus,
            remembr_client=remembr_client,
            index_path=path,
            max_elements=100,
        )
        idx1._model = mock_model
        import hnswlib

        idx1._index = hnswlib.Index(space="cosine", dim=384)
        idx1._index.init_index(max_elements=100, ef_construction=200, M=16)
        idx1._index.set_ef(50)

        vec = np.random.randn(384).astype(np.float32)
        mock_model.encode.return_value = vec
        idx1._add_entry_sync(
            "mem-1",
            "Trade AAPL BUY",
            {
                "decision": {
                    "symbol": "AAPL",
                    "direction": "BUY",
                    "timestamp": "2026-04-01T00:00:00+00:00",
                },
                "status": "open",
            },
        )

        await idx1.persist()

        assert os.path.exists(f"{path}.hnsw")
        assert os.path.exists(f"{path}.meta.json")

        idx2 = JournalIndexer(
            event_bus=event_bus,
            remembr_client=remembr_client,
            index_path=path,
            max_elements=100,
        )
        idx2._model = mock_model
        loaded = await idx2.load()

        assert loaded is True
        assert idx2.entry_count == 1
        assert "mem-1" in idx2._metadata
        assert "AAPL" in idx2._symbol_index

        results = idx2.search("Trade AAPL", limit=5)
        assert len(results) == 1
        assert results[0].memory_id == "mem-1"


@pytest.mark.asyncio
async def test_load_returns_false_when_no_files():
    event_bus = MagicMock()
    remembr_client = AsyncMock()
    idx = JournalIndexer(
        event_bus=event_bus,
        remembr_client=remembr_client,
        index_path="/tmp/nonexistent_path_xyz",
        max_elements=100,
    )
    assert await idx.load() is False


@pytest.mark.asyncio
async def test_handle_entry_added(indexer, mock_model):
    vec = np.ones(384, dtype=np.float32)
    vec /= np.linalg.norm(vec)
    mock_model.encode.return_value = vec

    await indexer._handle_entry_added(
        {
            "memory_id": "mem-99",
            "content": "Trade GOOG BUY high confidence",
            "metadata": {
                "decision": {
                    "symbol": "GOOG",
                    "direction": "BUY",
                    "timestamp": "2026-04-01T00:00:00+00:00",
                },
                "status": "open",
            },
        }
    )

    assert "mem-99" in indexer._metadata
    assert "GOOG" in indexer._symbol_index


@pytest.mark.asyncio
async def test_handle_entry_updated_tombstone(indexer, mock_model):
    vec = np.random.randn(384).astype(np.float32)
    mock_model.encode.return_value = vec
    indexer._add_entry_sync(
        "mem-1",
        "Trade AAPL BUY",
        {
            "decision": {
                "symbol": "AAPL",
                "direction": "BUY",
                "timestamp": "2026-04-01T00:00:00+00:00",
            },
            "status": "open",
        },
    )

    await indexer._handle_entry_updated(
        {
            "memory_id": "mem-1",
            "metadata": {
                "decision": {
                    "symbol": "AAPL",
                    "direction": "BUY",
                    "timestamp": "2026-04-01T00:00:00+00:00",
                },
                "status": "cancelled",
                "realized_pnl": -5.0,
            },
        }
    )

    assert indexer._metadata["mem-1"]["status"] == "cancelled"
    results = indexer.get_by_symbol("AAPL", limit=10)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_handle_entry_updated_ignores_unknown(indexer):
    await indexer._handle_entry_updated(
        {
            "memory_id": "nonexistent",
            "metadata": {"status": "closed"},
        }
    )
    assert "nonexistent" not in indexer._metadata


from unittest.mock import patch


@pytest.mark.asyncio
async def test_start_sets_up_background_tasks():
    event_bus = MagicMock()

    async def empty_gen():
        return
        yield

    event_bus.subscribe = empty_gen

    remembr_client = AsyncMock()
    remembr_client.list = AsyncMock(
        return_value={"data": [], "page": 1, "total_pages": 1}
    )

    with patch("journal.indexer.SentenceTransformer") as MockST:
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        MockST.return_value = mock_model

        idx = JournalIndexer(
            event_bus=event_bus,
            remembr_client=remembr_client,
            index_path="/tmp/test_start",
            max_elements=100,
        )
        await idx.start()

        assert idx._subscriber_task is not None
        assert idx._rehydrate_task is not None
        assert idx._model is not None
        assert idx._index is not None

        await idx._rehydrate_task
        assert idx.is_ready is True

        await idx.stop()


@pytest.mark.asyncio
async def test_stop_persists_and_cancels():
    event_bus = MagicMock()

    async def empty_gen():
        return
        yield

    event_bus.subscribe = empty_gen

    remembr_client = AsyncMock()
    remembr_client.list = AsyncMock(
        return_value={"data": [], "page": 1, "total_pages": 1}
    )

    with patch("journal.indexer.SentenceTransformer") as MockST:
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_model.encode.return_value = np.random.randn(384).astype(np.float32)
        MockST.return_value = mock_model

        idx = JournalIndexer(
            event_bus=event_bus,
            remembr_client=remembr_client,
            index_path="/tmp/test_stop",
            max_elements=100,
        )
        await idx.start()
        await idx._rehydrate_task

        idx._add_entry_sync(
            "mem-1",
            "Trade AAPL",
            {
                "decision": {
                    "symbol": "AAPL",
                    "direction": "BUY",
                    "timestamp": "2026-04-01T00:00:00+00:00",
                },
                "status": "open",
            },
        )

        await idx.stop()

        assert idx._subscriber_task.cancelled() or idx._subscriber_task.done()


@pytest.mark.asyncio
async def test_rehydrate_fail_open():
    event_bus = MagicMock()

    async def empty_gen():
        return
        yield

    event_bus.subscribe = empty_gen

    remembr_client = AsyncMock()
    remembr_client.list = AsyncMock(side_effect=Exception("Network error"))

    with patch("journal.indexer.SentenceTransformer") as MockST:
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        MockST.return_value = mock_model

        idx = JournalIndexer(
            event_bus=event_bus,
            remembr_client=remembr_client,
            index_path="/tmp/test_failopen",
            max_elements=100,
        )
        await idx.start()
        await idx._rehydrate_task

        assert idx.is_ready is True
        assert idx.entry_count == 0

        await idx.stop()


@pytest.mark.asyncio
async def test_rehydrate_indexes_entries():
    event_bus = MagicMock()

    async def empty_gen():
        return
        yield

    event_bus.subscribe = empty_gen

    remembr_client = AsyncMock()
    remembr_client.list = AsyncMock(
        return_value={
            "data": [
                {
                    "id": "mem-1",
                    "value": "Trade AAPL BUY",
                    "metadata": {
                        "decision": {
                            "symbol": "AAPL",
                            "direction": "BUY",
                            "timestamp": "2026-04-01T00:00:00+00:00",
                        },
                        "status": "open",
                    },
                },
                {
                    "id": "mem-2",
                    "value": "Trade TSLA SELL",
                    "metadata": {
                        "decision": {
                            "symbol": "TSLA",
                            "direction": "SELL",
                            "timestamp": "2026-04-01T01:00:00+00:00",
                        },
                        "status": "closed",
                    },
                },
            ],
            "page": 1,
            "total_pages": 1,
        }
    )

    with patch("journal.indexer.SentenceTransformer") as MockST:
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        def _mock_encode(texts, **kwargs):
            if isinstance(texts, list):
                return np.random.randn(len(texts), 384).astype(np.float32)
            return np.random.randn(384).astype(np.float32)
        mock_model.encode.side_effect = _mock_encode
        MockST.return_value = mock_model

        idx = JournalIndexer(
            event_bus=event_bus,
            remembr_client=remembr_client,
            index_path="/tmp/test_rehydrate_entries",
            max_elements=100,
        )
        await idx.start()
        await idx._rehydrate_task

        assert idx.is_ready is True
        assert idx.entry_count == 2
        assert "AAPL" in idx._symbol_index
        assert "TSLA" in idx._symbol_index

        await idx.stop()
