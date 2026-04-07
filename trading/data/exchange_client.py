import ccxt.async_support as ccxt
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ExchangeClient:
    """Wrapper for CCXT to fetch real-time data for AnomalyProvider and others."""
    
    def __init__(self, exchange_id: str = 'binance'):
        self.exchange_id = exchange_id
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            'enableRateLimit': True,
        })
        
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker information including volume and spread."""
        try:
            # Map BTCUSD to BTC/USDT if necessary based on exchange
            formatted_symbol = symbol.replace("USD", "/USDT")
            ticker = await self.exchange.fetch_ticker(formatted_symbol)
            return ticker
        except Exception as e:
            logger.warning(f"ExchangeClient failed to fetch ticker for {symbol}: {e}")
            return {}

    async def fetch_funding_rate(self, symbol: str) -> float:
        """Fetch current funding rate if applicable (e.g. perpetual swaps)."""
        try:
            formatted_symbol = symbol.replace("USD", "/USDT:USDT")
            funding = await self.exchange.fetch_funding_rate(formatted_symbol)
            return funding.get('fundingRate', 0.0)
        except Exception as e:
            logger.warning(f"ExchangeClient failed to fetch funding rate for {symbol}: {e}")
            return 0.0

    async def close(self):
        await self.exchange.close()
