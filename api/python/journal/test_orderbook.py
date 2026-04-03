import unittest
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from journal.orderbook import Orderbook, PolymarketWSClient


class TestOrderbook(unittest.TestCase):
    def setUp(self):
        self.book = Orderbook("TEST-MARKET")

    def test_bid_sorting(self):
        self.book.update("buy", 100.0, 10.0)
        self.book.update("buy", 105.0, 5.0)
        self.book.update("buy", 95.0, 20.0)

        prices = [level[0] for level in self.book.bids]
        self.assertEqual(prices, [105.0, 100.0, 95.0])
        self.assertEqual(self.book.get_best_bid(), (105.0, 5.0))

    def test_ask_sorting(self):
        self.book.update("sell", 110.0, 10.0)
        self.book.update("sell", 108.0, 5.0)
        self.book.update("sell", 115.0, 20.0)

        prices = [level[0] for level in self.book.asks]
        self.assertEqual(prices, [108.0, 110.0, 115.0])
        self.assertEqual(self.book.get_best_ask(), (108.0, 5.0))

    def test_liquidity_at_price(self):
        self.book.update("buy", 100.0, 10.0)
        self.book.update("buy", 99.0, 10.0)
        self.book.update("buy", 98.0, 10.0)

        self.assertEqual(self.book.get_liquidity_at_price("buy", 99.0), 20.0)
        self.assertEqual(self.book.get_liquidity_at_price("buy", 101.0), 0.0)

    def test_removal(self):
        self.book.update("buy", 100.0, 10.0)
        self.assertEqual(len(self.book.bids), 1)

        self.book.update("buy", 100.0, 0.0)
        self.assertEqual(len(self.book.bids), 0)

    def test_age_ms_starts_infinite(self):
        self.assertEqual(self.book.age_ms, float('inf'))

    def test_age_ms_updates_on_write(self):
        self.book.update("buy", 100.0, 10.0)
        # Should be very recent — within 100ms
        self.assertLess(self.book.age_ms, 100.0)

    def test_empty_book_returns_none(self):
        self.assertIsNone(self.book.get_best_bid())
        self.assertIsNone(self.book.get_best_ask())


class TestPolymarketWSClientStaleness(unittest.TestCase):
    def setUp(self):
        self.client = PolymarketWSClient(
            tickers=["TICKER-A"],
            stale_threshold_ms=50.0,
        )

    def test_stale_when_never_updated(self):
        self.assertTrue(self.client.is_stale("TICKER-A"))

    def test_not_stale_after_fresh_update(self):
        self.client.cache["TICKER-A"].update("buy", 0.65, 100.0)
        self.assertFalse(self.client.is_stale("TICKER-A"))

    def test_stale_for_unknown_ticker(self):
        self.assertTrue(self.client.is_stale("UNKNOWN"))

    def test_preflight_rejects_stale_data(self):
        # Never updated, so stale — should reject even if liquidity would be sufficient
        self.client.cache["TICKER-A"].bids = [[0.65, 1000.0]]
        result = self.client.check_preflight_slippage("TICKER-A", "buy", 0.60, 10.0)
        self.assertFalse(result)

    def test_preflight_passes_with_fresh_data(self):
        self.client.cache["TICKER-A"].update("buy", 0.65, 100.0)
        result = self.client.check_preflight_slippage("TICKER-A", "buy", 0.60, 10.0)
        self.assertTrue(result)

    def test_preflight_fails_with_insufficient_liquidity(self):
        self.client.cache["TICKER-A"].update("buy", 0.65, 5.0)
        result = self.client.check_preflight_slippage("TICKER-A", "buy", 0.60, 10.0)
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
