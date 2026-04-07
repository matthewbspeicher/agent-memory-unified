import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import numpy as np

# Add sdk-python to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from remembr.turbo import TurboQuantIndex

class TestTurboQuantIndexSync(unittest.TestCase):
    def setUp(self):
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

    def test_update_memory(self):
        # 1. Add initial memory
        memory_id = "trade_1"
        initial_text = "Intent to buy BTC"
        self.mock_model.encode.return_value = np.zeros(384)
        
        self.index.add(memory_id, initial_text, {"status": "open"})
        self.assertEqual(self.index._current_id, 1)
        self.assertIn(memory_id, self.index._id_to_internal)
        
        # 2. Update memory
        updated_text = "Closed BTC trade with $500 PnL"
        self.mock_model.encode.return_value = np.ones(384)
        
        self.index.update(memory_id, updated_text, {"status": "closed", "pnl": 500})
        
        # Verify mark_deleted was called for the old internal ID (0)
        self.mock_index.mark_deleted.assert_called_once_with(0)
        
        # Verify new item added with internal ID 1
        self.assertEqual(self.index._id_to_internal[memory_id], 1)
        self.assertEqual(self.index._current_id, 2)
        self.assertEqual(self.index.metadata_cache[1]["pnl"], 500)
        self.assertNotIn(0, self.index.metadata_cache)

    def test_delete_memory(self):
        memory_id = "trade_2"
        self.index.add(memory_id, "test", {})
        self.index.delete(memory_id)
        
        self.mock_index.mark_deleted.assert_called_once()
        self.assertNotIn(memory_id, self.index._id_to_internal)
        self.assertNotIn(0, self.index.metadata_cache)

if __name__ == '__main__':
    unittest.main()
