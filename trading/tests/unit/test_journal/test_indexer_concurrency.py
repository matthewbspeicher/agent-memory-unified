import asyncio
import sys
from unittest.mock import patch, MagicMock

# sys.modules mocks removed to prevent test pollution

import numpy as np

import pytest

from journal.indexer import JournalIndexer
from data.events import EventBus

@pytest.mark.asyncio
async def test_indexer_concurrency():
    bus = EventBus()
    
    # Mock client
    from unittest.mock import AsyncMock
    client = MagicMock()
    client.list = AsyncMock(return_value={"data": []})
    
    indexer = JournalIndexer(
        event_bus=bus,
        remembr_client=client,
        index_path="/tmp/test_index"
    )
    
    # Mock load to skip reading disk, and _persist_sync to avoid file creation
    with patch.object(indexer, "load", return_value=False), \
         patch.object(indexer, "_persist_sync"), \
         patch("journal.indexer.SentenceTransformer") as MockST:
        
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_model.encode.return_value = np.random.randn(1, 384).astype(np.float32)
        MockST.return_value = mock_model

        await indexer.start()
    
        class CountingLock:
            def __init__(self):
                self.lock = __import__('threading').Lock()
                self.acquisitions = 0
            
            def acquire(self, blocking=True, timeout=-1):
                self.acquisitions += 1
                return self.lock.acquire(blocking, timeout)
            
            def release(self):
                self.lock.release()
                
            def __enter__(self):
                self.acquire()
                return self
                
            def __exit__(self, exc_type, exc_val, exc_tb):
                self.release()
        
        counting_lock = CountingLock()
        indexer._lock = counting_lock
    
        # Trigger 5 concurrent additions
        coros = [
            indexer._add_entry_async(f"mem{i}", f"content {i}", {"k": "v"})
            for i in range(5)
        ]
    
        await asyncio.gather(*coros)
    
        assert counting_lock.acquisitions == 5
        assert indexer._next_label == 5
        assert len(indexer._id_map) == 5
    
        await indexer.stop()
