import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

# hnswlib is imported lazily inside journal/indexer.py's ensure_model; skip
# the test file entirely when it's not installed (CI minimal install, dev
# containers without `pip install -e .[ml]`). sentence_transformers is
# mocked below so it doesn't need the importorskip.
pytest.importorskip("hnswlib")

import numpy as np

# Mock sentence_transformers BEFORE importing JournalIndexer to avoid crashes
sys.modules["sentence_transformers"] = MagicMock()

from journal.indexer import JournalIndexer


@pytest.fixture
def mock_model():
    model = MagicMock()
    # Default return value for encode
    model.get_sentence_embedding_dimension.return_value = 384
    model.encode.return_value = np.zeros(384, dtype=np.float32)
    return model


@pytest.fixture
def indexer(mock_model):
    event_bus = MagicMock()
    remembr_client = AsyncMock()
    idx = JournalIndexer(
        event_bus=event_bus,
        remembr_client=remembr_client,
        index_path="/tmp/test_indexer_sync",
        max_elements=100,
    )
    idx._model = mock_model
    import hnswlib

    idx._index = hnswlib.Index(space="cosine", dim=384)
    idx._index.init_index(max_elements=100, ef_construction=200, M=16)
    idx._index.set_ef(50)
    idx.is_ready = True
    return idx


@pytest.mark.asyncio
async def test_semantic_drift_reembedding(indexer, mock_model):
    dim = 384
    # 0. Setup deterministic vectors
    initial_vec = np.zeros(dim, dtype=np.float32)
    initial_vec[0] = 1.0

    updated_vec = np.zeros(dim, dtype=np.float32)
    updated_vec[1] = 1.0

    nearby_vec = np.zeros(dim, dtype=np.float32)
    nearby_vec[0] = 0.9
    nearby_vec[2] = 0.1

    # 1. Add dummies
    for i in range(5):
        vec = np.zeros(dim, dtype=np.float32)
        vec[i + 2] = 1.0
        mock_model.encode.return_value = vec
        await indexer._handle_entry_added(
            {"memory_id": f"dummy-{i}", "content": f"dummy {i}", "metadata": {}}
        )

    # Add nearby dummy
    mock_model.encode.return_value = nearby_vec
    await indexer._handle_entry_added(
        {"memory_id": "nearby-1", "content": "nearby", "metadata": {}}
    )

    # 2. Add initial entry
    initial_content = "The market is bullish on AAPL"
    mock_model.encode.return_value = initial_vec
    memory_id = "mem-1"
    metadata = {"decision": {"symbol": "AAPL"}, "status": "open"}

    await indexer._handle_entry_added(
        {"memory_id": memory_id, "content": initial_content, "metadata": metadata}
    )

    old_label = indexer._id_map[memory_id]

    # Verify we can find it
    mock_model.encode.return_value = initial_vec
    results = indexer.search("bullish AAPL")
    assert any(r.memory_id == memory_id for r in results)

    # 3. Update the entry
    updated_content = "The weather in London is rainy"
    mock_model.encode.return_value = updated_vec

    await indexer._handle_entry_updated(
        {"memory_id": memory_id, "content": updated_content, "metadata": metadata}
    )

    new_label = indexer._id_map[memory_id]

    # 4. Verify tombstone count and label mapping
    assert indexer._tombstone_count == 1
    assert old_label not in indexer._label_to_id
    assert indexer._label_to_id[new_label] == memory_id

    # 5. Search for NEW text
    mock_model.encode.return_value = updated_vec
    results = indexer.search("rainy London")
    # mem-1 should be the TOP result for new text
    assert results[0].memory_id == memory_id
    assert results[0].score > 0.99

    # 6. Search for OLD text (initial_vec)
    mock_model.encode.return_value = initial_vec
    results = indexer.search("bullish AAPL")

    # nearby-1 should be the TOP result for old text now because mem-1 was re-embedded
    assert results[0].memory_id == "nearby-1"
    assert results[0].memory_id != memory_id

    # Check that score for mem-1 is very low for old text
    mem_result = next((r for r in results if r.memory_id == memory_id), None)
    if mem_result:
        # Cosine distance between [1,0,0...] and [0,1,0...] is 1.0, score 0.0
        assert mem_result.score < 0.01
