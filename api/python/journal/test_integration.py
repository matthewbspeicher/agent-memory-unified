import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import sys
import os
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'sdk-python')))

from python.journal.event_bus import EventBus
from python.journal.turboquant import TurboQuantIndexer, EVENT_TRADE_CREATED, EVENT_TRADE_UPDATED, EVENT_TRADE_DELETED


def run_async(coro):
    """Helper to run async tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestEventBus(unittest.TestCase):
    def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("test.event", handler)
        run_async(bus.emit("test.event", {"data": "hello"}))

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["data"], "hello")

    def test_multiple_handlers(self):
        bus = EventBus()
        results = []

        async def handler_a(event):
            results.append("a")

        async def handler_b(event):
            results.append("b")

        bus.subscribe("test.event", handler_a)
        bus.subscribe("test.event", handler_b)
        run_async(bus.emit("test.event", {}))

        self.assertEqual(results, ["a", "b"])

    def test_unsubscribe(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("test.event", handler)
        bus.unsubscribe("test.event", handler)
        run_async(bus.emit("test.event", {"data": "should not arrive"}))

        self.assertEqual(len(received), 0)

    def test_handler_error_does_not_break_bus(self):
        bus = EventBus()
        results = []

        async def bad_handler(event):
            raise ValueError("boom")

        async def good_handler(event):
            results.append("ok")

        bus.subscribe("test.event", bad_handler)
        bus.subscribe("test.event", good_handler)
        run_async(bus.emit("test.event", {}))

        # good_handler should still run even though bad_handler threw
        self.assertEqual(results, ["ok"])


class TestTurboQuantIndexerEventWiring(unittest.TestCase):
    def setUp(self):
        self.mock_client = AsyncMock()
        self.mock_model = MagicMock()
        self.mock_index = MagicMock()

        self.patcher_model = patch('remembr.turbo.SentenceTransformer', return_value=self.mock_model)
        self.patcher_index = patch('remembr.turbo.hnswlib.Index', return_value=self.mock_index)

        self.patcher_model.start()
        self.patcher_index.start()

        self.indexer = TurboQuantIndexer(client=self.mock_client, persist_path="/tmp/test_turboquant")
        self.indexer.is_ready = True
        self.bus = EventBus()
        self.indexer.subscribe(self.bus)

    def tearDown(self):
        self.patcher_model.stop()
        self.patcher_index.stop()

    def test_create_event_adds_to_index(self):
        self.mock_model.encode.return_value = np.zeros(384)

        event = {
            "data": {
                "id": "trade_001",
                "value": "Opened long AAPL at $150",
                "metadata": {
                    "realized_pnl": None,
                    "status": "open",
                    "decision": {"direction": "long"},
                    "ticker": "AAPL",
                }
            }
        }

        run_async(self.bus.emit(EVENT_TRADE_CREATED, event))

        # Verify the index received an add
        self.mock_index.add_items.assert_called_once()
        self.assertIn("trade_001", self.indexer.index._id_to_internal)
        meta = self.indexer.index.metadata_cache[0]
        self.assertEqual(meta["_memory_id"], "trade_001")
        self.assertEqual(meta["status"], "open")

    def test_update_event_replaces_in_index(self):
        self.mock_model.encode.return_value = np.zeros(384)

        # First, create
        create_event = {
            "data": {
                "id": "trade_002",
                "value": "Opened short TSLA",
                "metadata": {"status": "open", "decision": {"direction": "short"}}
            }
        }
        run_async(self.bus.emit(EVENT_TRADE_CREATED, create_event))

        # Then, update with PnL
        self.mock_model.encode.return_value = np.ones(384)
        update_event = {
            "data": {
                "id": "trade_002",
                "value": "Closed short TSLA with $500 PnL",
                "metadata": {
                    "status": "closed",
                    "realized_pnl": 500,
                    "decision": {"direction": "short"},
                }
            }
        }
        run_async(self.bus.emit(EVENT_TRADE_UPDATED, update_event))

        # Old internal ID (0) should be marked deleted
        self.mock_index.mark_deleted.assert_called_once_with(0)

        # New internal ID (1) should have updated metadata
        self.assertIn("trade_002", self.indexer.index._id_to_internal)
        new_internal = self.indexer.index._id_to_internal["trade_002"]
        self.assertEqual(new_internal, 1)
        self.assertEqual(self.indexer.index.metadata_cache[1]["realized_pnl"], 500)
        self.assertEqual(self.indexer.index.metadata_cache[1]["status"], "closed")

    def test_delete_event_removes_from_index(self):
        self.mock_model.encode.return_value = np.zeros(384)

        # Create first
        create_event = {
            "data": {
                "id": "trade_003",
                "value": "Test trade",
                "metadata": {"status": "open", "decision": {"direction": "long"}}
            }
        }
        run_async(self.bus.emit(EVENT_TRADE_CREATED, create_event))
        self.assertIn("trade_003", self.indexer.index._id_to_internal)

        # Delete
        delete_event = {"data": {"id": "trade_003"}}
        run_async(self.bus.emit(EVENT_TRADE_DELETED, delete_event))

        self.mock_index.mark_deleted.assert_called_once()
        self.assertNotIn("trade_003", self.indexer.index._id_to_internal)

    def test_search_falls_back_to_remote_on_failure(self):
        self.mock_model.encode.side_effect = RuntimeError("model crashed")
        self.mock_client.search = AsyncMock(return_value=[{"id": "remote_1", "value": "fallback"}])

        results = run_async(self.indexer.search_trades("test query"))

        self.mock_client.search.assert_called_once()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "remote_1")

    def test_search_falls_back_when_not_ready(self):
        self.indexer.is_ready = False
        self.mock_client.search = AsyncMock(return_value=[{"id": "remote_2"}])

        results = run_async(self.indexer.search_trades("test"))

        self.mock_client.search.assert_called_once()
        self.assertEqual(results[0]["id"], "remote_2")

    def test_dirty_flag_tracks_mutations(self):
        self.mock_model.encode.return_value = np.zeros(384)

        self.assertFalse(self.indexer.index.is_dirty)

        event = {"data": {"id": "t1", "value": "test", "metadata": {"status": "open", "decision": {}}}}
        run_async(self.bus.emit(EVENT_TRADE_CREATED, event))

        self.assertTrue(self.indexer.index.is_dirty)


if __name__ == '__main__':
    unittest.main()
