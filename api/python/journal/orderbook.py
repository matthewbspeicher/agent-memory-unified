import asyncio
import json
import logging
import threading
import time
from typing import Dict, List, Optional, Tuple
from bisect import bisect_left, insort

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OrderbookCache")


class Orderbook:
    """
    In-memory L2 Orderbook for a single market.
    Maintains sorted bids and asks for O(log N) updates and O(1) top-of-book access.
    Thread-safe via RLock for concurrent read/write protection.
    """
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.bids: List[List[float]] = []  # [[price, size], ...] sorted by price DESC
        self.asks: List[List[float]] = []  # [[price, size], ...] sorted by price ASC
        self.last_update_id = 0
        self.last_update_time: float = 0.0
        self._lock = threading.RLock()

    def update(self, side: str, price: float, size: float):
        """Update or remove a price level. Thread-safe."""
        with self._lock:
            book = self.bids if side == 'buy' else self.asks
            prices = [level[0] for level in book]

            # Binary search for the price level
            idx = bisect_left(prices, price) if side == 'sell' else bisect_left([-p for p in prices], -price)

            if idx < len(book) and book[idx][0] == price:
                if size == 0:
                    book.pop(idx)
                else:
                    book[idx][1] = size
            elif size > 0:
                if side == 'buy':
                    insort(book, [price, size], key=lambda x: -x[0])
                else:
                    insort(book, [price, size], key=lambda x: x[0])

            self.last_update_time = time.monotonic()

    def get_best_bid(self) -> Optional[Tuple[float, float]]:
        with self._lock:
            return tuple(self.bids[0]) if self.bids else None

    def get_best_ask(self) -> Optional[Tuple[float, float]]:
        with self._lock:
            return tuple(self.asks[0]) if self.asks else None

    def get_liquidity_at_price(self, side: str, target_price: float) -> float:
        """Returns cumulative size available at or better than the target price."""
        with self._lock:
            book = self.bids if side == 'buy' else self.asks
            total_size = 0.0

            for price, size in book:
                if side == 'buy' and price >= target_price:
                    total_size += size
                elif side == 'sell' and price <= target_price:
                    total_size += size
                else:
                    break
            return total_size

    @property
    def age_ms(self) -> float:
        """Milliseconds since the last update. Returns inf if never updated."""
        with self._lock:
            if self.last_update_time == 0.0:
                return float('inf')
            return (time.monotonic() - self.last_update_time) * 1000


class PolymarketWSClient:
    """
    WebSocket client for Polymarket CLOB L2 data.
    Features: staleness monitoring, REST snapshot re-sync on reconnect, thread-safe cache.
    """
    def __init__(
        self,
        tickers: List[str],
        uri: str = "wss://clob.polymarket.com/ws/l2",
        rest_base: str = "https://clob.polymarket.com",
        stale_threshold_ms: float = 500.0,
    ):
        self.tickers = tickers
        self.uri = uri
        self.rest_base = rest_base
        self.stale_threshold_ms = stale_threshold_ms
        self.cache: Dict[str, Orderbook] = {t: Orderbook(t) for t in tickers}
        self.is_running = False

    async def connect(self):
        """Main connection and message loop with re-sync on reconnect."""
        import websockets

        async for websocket in websockets.connect(self.uri):
            try:
                self.is_running = True

                # Re-sync from REST snapshot on every (re)connect
                await self._resync_from_rest()

                subscribe_msg = {
                    "type": "subscribe",
                    "assets": self.tickers,
                    "channels": ["l2_updates"]
                }
                await websocket.send(json.dumps(subscribe_msg))
                logger.info(f"Subscribed to {self.tickers} on {self.uri}")

                async for message in websocket:
                    await self._handle_message(message)
            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed. Reconnecting with REST re-sync...")
                continue
            except Exception as e:
                logger.error(f"Unexpected error in WS loop: {e}")
                self.is_running = False
                break

    async def _resync_from_rest(self):
        """Fetch L2 snapshot from REST API to seed the cache after (re)connect."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                for ticker in self.tickers:
                    url = f"{self.rest_base}/book?token_id={ticker}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            book = self.cache[ticker]
                            # Clear existing state
                            with book._lock:
                                book.bids.clear()
                                book.asks.clear()
                            # Apply snapshot
                            for bid in data.get("bids", []):
                                book.update("buy", float(bid["price"]), float(bid["size"]))
                            for ask in data.get("asks", []):
                                book.update("sell", float(ask["price"]), float(ask["size"]))
                            logger.info(f"REST re-sync complete for {ticker}: {len(book.bids)} bids, {len(book.asks)} asks")
                        else:
                            logger.warning(f"REST re-sync failed for {ticker}: HTTP {resp.status}")
        except ImportError:
            logger.warning("aiohttp not installed, skipping REST re-sync")
        except Exception as e:
            logger.error(f"REST re-sync failed: {e}")

    async def _handle_message(self, message: str):
        data = json.loads(message)

        if data.get("type") == "l2_updates":
            ticker = data.get("asset_id")
            if ticker not in self.cache:
                return

            book = self.cache[ticker]
            for change in data.get("changes", []):
                side = 'buy' if change[0] == 'BUY' else 'sell'
                price = float(change[1])
                size = float(change[2])
                book.update(side, price, size)

    def is_stale(self, ticker: str) -> bool:
        """True if the orderbook data for this ticker is older than the stale threshold."""
        if ticker not in self.cache:
            return True
        return self.cache[ticker].age_ms > self.stale_threshold_ms

    def check_preflight_slippage(self, ticker: str, side: str, price: float, min_size: float) -> bool:
        """
        O(depth) pre-flight check against local cache.
        Returns False if data is stale to prevent executing on outdated prices.
        """
        if ticker not in self.cache:
            return False

        if self.is_stale(ticker):
            logger.warning(f"Stale orderbook for {ticker} ({self.cache[ticker].age_ms:.0f}ms old), rejecting preflight")
            return False

        available_size = self.cache[ticker].get_liquidity_at_price(side, price)
        return available_size >= min_size
