import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add sdk-python to path so we can import remembr
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from remembr.trading import TradingJournal
from remembr.turbo import TurboQuantIndex
from remembr.models import TradeResult, BulkImportResult
from remembr.client import RemembrClient

class TestTradingJournal(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=RemembrClient)
        self.journal = TradingJournal(self.mock_client, paper=True)

    def test_execute_trade_success(self):
        # Mock store response
        self.mock_client.store.return_value = {"id": "mem_123"}
        # Mock post response
        self.mock_client.post.return_value = {
            "id": "trade_456",
            "ticker": "BTC/USD",
            "direction": "buy",
            "price": 50000.0,
            "quantity": 1.0,
            "status": "open",
            "memory_id": "mem_123"
        }

        result = self.journal.execute_trade(
            ticker="BTC/USD",
            direction="buy",
            quantity=1.0,
            price=50000.0,
            reasoning="Bullish momentum"
        )

        # Verify memory created
        self.mock_client.store.assert_called_once()
        args, kwargs = self.mock_client.store.call_args
        self.assertEqual(kwargs["value"], "Bullish momentum")
        self.assertEqual(kwargs["metadata"]["type"], "trade_decision")

        # Verify trade created with memory_id
        self.mock_client.post.assert_called_once_with(
            "/trading/trades",
            json={
                "ticker": "BTC/USD",
                "direction": "buy",
                "quantity": 1.0,
                "price": 50000.0,
                "memory_id": "mem_123",
                "paper": True
            }
        )
        self.assertIsInstance(result, TradeResult)
        self.assertEqual(result.id, "trade_456")

    def test_execute_trade_memory_failure(self):
        # Mock store failure (empty response or missing ID)
        self.mock_client.store.return_value = {}
        
        with self.assertRaises(Exception) as cm:
            self.journal.execute_trade(
                ticker="BTC/USD",
                direction="buy",
                quantity=1.0,
                price=50000.0,
                reasoning="Bullish momentum"
            )
        
        self.assertIn("Failed to retrieve memory_id", str(cm.exception))
        # Verify trade NOT created
        self.mock_client.post.assert_not_called()

    def test_close_trade_success(self):
        self.mock_client.store.return_value = {"id": "mem_exit_123"}
        self.mock_client.post.return_value = {
            "id": "trade_exit_456",
            "parent_trade_id": "trade_456",
            "price": 51000.0,
            "quantity": 1.0,
            "status": "closed"
        }

        result = self.journal.close_trade(
            parent_trade_id="trade_456",
            price=51000.0,
            reasoning="Take profit reached"
        )

        self.mock_client.store.assert_called_once()
        self.mock_client.post.assert_called_once()
        self.assertEqual(result.status, "closed")

    def test_close_all(self):
        # Mock get_path to return parent trade info
        self.mock_client.get_path.return_value = {"data": {"quantity": 1.5}}
        self.mock_client.store.return_value = {"id": "mem_exit_all"}
        self.mock_client.post.return_value = {
            "id": "trade_exit_all", 
            "status": "closed",
            "price": 52000.0,
            "quantity": 1.5
        }

        result = self.journal.close_all(
            parent_trade_id="trade_789",
            price=52000.0,
            reasoning="Closing all"
        )

        # Verify get parent then close
        self.mock_client.get_path.assert_called_once_with("/trading/trades/trade_789")
        self.mock_client.post.assert_called_once()
        # Verify quantity was passed correctly
        call_args = self.mock_client.post.call_args
        self.assertEqual(call_args.kwargs["json"]["quantity"], 1.5)

    def test_bulk_import_trades(self):
        trades = [
            {"ticker": "ETH/USD", "direction": "buy", "quantity": 10, "price": 2500},
            {"ticker": "SOL/USD", "direction": "buy", "quantity": 100, "price": 100}
        ]
        self.mock_client.post.return_value = {
            "data": {
                "total": 2,
                "succeeded": 2,
                "failed": 0,
                "errors": []
            }
        }

        result = self.journal.bulk_import_trades(trades)

        self.mock_client.post.assert_called_once_with(
            "/trading/trades/bulk",
            json={"trades": trades, "paper": True}
        )
        self.assertIsInstance(result, BulkImportResult)
        self.assertEqual(result.total, 2)

class TestTurboQuantIndex(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=RemembrClient)
        self.loader = TurboQuantIndex(self.mock_client)

    def test_load_context_success(self):
        # Mock turboquant module
        mock_turboquant = MagicMock()
        mock_turboquant.compress_to_cache.return_value = "mock_cache_object"
        
        with patch.dict(sys.modules, {'turboquant': mock_turboquant}):
            self.mock_client.search.return_value = [{"value": "mem1"}, {"value": "mem2"}]
            
            result = self.loader.load_context(q="test query", model="gpt-4")
            
            self.assertEqual(result, "mock_cache_object")
            mock_turboquant.compress_to_cache.assert_called_once_with("mem1\nmem2", model_id="gpt-4")

    def test_load_context_no_turboquant(self):
        # Ensure turboquant is NOT in sys.modules and ImportError is raised
        with patch.dict(sys.modules, {'turboquant': MagicMock()}):
            with patch.dict(sys.modules, {'turboquant': None}):
                with self.assertRaises(ImportError) as cm:
                    self.loader.load_context(q="test", model="test-model")
                
                self.assertIn("turboquant is not installed", str(cm.exception))

if __name__ == '__main__':
    unittest.main()
