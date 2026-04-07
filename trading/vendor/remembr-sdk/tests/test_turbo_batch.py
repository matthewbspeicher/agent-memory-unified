import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import numpy as np

# Add sdk-python to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from remembr.turbo import TurboQuantIndex

class TestTurboQuantIndexBatch(unittest.TestCase):
    def setUp(self):
        # Mock sentence_transformers and hnswlib to avoid OMP errors and dependencies
        self.mock_model = MagicMock()
        self.mock_index = MagicMock()
        
        # Patch where they are USED
        self.patcher_model = patch('remembr.turbo.SentenceTransformer', return_value=self.mock_model)
        self.patcher_index = patch('remembr.turbo.hnswlib.Index', return_value=self.mock_index)
        
        self.patcher_model.start()
        self.patcher_index.start()
        
        self.index = TurboQuantIndex()

    def tearDown(self):
        self.patcher_model.stop()
        self.patcher_index.stop()

    def test_add_batch(self):
        ids = ["mem1", "mem2"]
        texts = ["text1", "text2"]
        metadatas = [{"pnl": 10}, {"pnl": -5}]
        
        # Mock embeddings
        mock_vectors = np.random.rand(2, 384).astype('float32')
        self.mock_model.encode.return_value = mock_vectors
        
        self.index.add_batch(ids, texts, metadatas)
        
        # Verify model.encode was called with the batch
        self.mock_model.encode.assert_called_once_with(texts)
        
        # Verify hnswlib.add_items was called with vectors and internal IDs
        self.mock_index.add_items.assert_called_once()
        args, _ = self.mock_index.add_items.call_args
        np.testing.assert_array_equal(args[0], mock_vectors)
        self.assertEqual(list(args[1]), [0, 1])
        
        # Verify metadata cache
        self.assertEqual(self.index.metadata_cache[0]["_memory_id"], "mem1")
        self.assertEqual(self.index.metadata_cache[0]["pnl"], 10)
        self.assertEqual(self.index.metadata_cache[1]["_memory_id"], "mem2")
        self.assertEqual(self.index.metadata_cache[1]["pnl"], -5)
        
        # Verify id mapping
        self.assertEqual(self.index._id_to_internal["mem1"], 0)
        self.assertEqual(self.index._id_to_internal["mem2"], 1)
        self.assertEqual(self.index._current_id, 2)

if __name__ == '__main__':
    unittest.main()
