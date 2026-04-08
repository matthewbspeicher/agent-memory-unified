from __future__ import annotations
import logging
from typing import Any

from broker.models import Quote, Symbol, Bar
from data.sources.base import DataSource
from data.exchange_client import ExchangeClient

logger = logging.getLogger(__name__)

class ExchangeDataSource(DataSource):
    """Data source using CCXT via ExchangeClient."""
    
    supports_quotes = True
    supports_order_book = True
    
    def __init__(self, exchange_id: str = "binance"):
        self._client = ExchangeClient(exchange_id=exchange_id)
        
    async def get_quote(self, symbol: Symbol) -> Quote:
        ticker = await self._client.fetch_ticker(symbol.ticker)
        if not ticker:
            return Quote(symbol=symbol, bid=None, ask=None, last=None, volume=0)
            
        from decimal import Decimal
        return Quote(
            symbol=symbol,
            bid=Decimal(str(ticker.get('bid'))) if ticker.get('bid') else None,
            ask=Decimal(str(ticker.get('ask'))) if ticker.get('ask') else None,
            last=Decimal(str(ticker.get('last'))) if ticker.get('last') else None,
            volume=int(float(ticker.get('baseVolume', 0))),
            timestamp=None # CCXT has 'timestamp' but Quote models it differently
        )

    async def get_order_book(self, symbol: Symbol, limit: int = 20) -> dict:
        """Fetch real-time order book for slippage estimation."""
        ticker_map = {"BTCUSD": "BTC/USDT", "ETHUSD": "ETH/USDT", "SOLUSD": "SOL/USDT"}
        ccxt_symbol = ticker_map.get(symbol.ticker, symbol.ticker.replace("USD", "/USDT"))
        
        try:
            return await self._client.exchange.fetch_order_book(ccxt_symbol, limit=limit)
        except Exception as e:
            logger.warning(f"ExchangeDataSource failed to fetch order book for {symbol.ticker}: {e}")
            return {"bids": [], "asks": []}

    async def close(self):
        await self._client.close()
