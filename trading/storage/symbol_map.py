from __future__ import annotations
import logging
from typing import Optional
from broker.models import Symbol, AssetType

logger = logging.getLogger(__name__)


class SignalMapper:
    """
    Translates external signal symbols (e.g. BTCUSD) to internal Symbols and broker tickers.
    """

    # Default mappings for Subnet 8
    DEFAULT_MAP = {
        "BTCUSD": {"ticker": "BTC/USD", "asset_type": AssetType.STOCK},
        "ETHUSD": {"ticker": "ETH/USD", "asset_type": AssetType.STOCK},
        "EURUSD": {"ticker": "EUR/USD", "asset_type": AssetType.FOREX},
        "GBPUSD": {"ticker": "GBP/USD", "asset_type": AssetType.FOREX},
        "XAUUSD": {"ticker": "XAU/USD", "asset_type": AssetType.STOCK},
    }

    def __init__(self, custom_map: Optional[dict] = None):
        self._map = self.DEFAULT_MAP.copy()
        if custom_map:
            self._map.update(custom_map)

    def map_to_symbol(self, external_symbol: str) -> Optional[Symbol]:
        """Maps an external string like 'BTCUSD' to a Symbol object."""
        entry = self._map.get(external_symbol)
        if not entry:
            # Try fuzzy match or default to CRYPTO if it looks like one
            if len(external_symbol) == 6:  # e.g. BTCUSD
                return Symbol(
                    ticker=f"{external_symbol[:3]}/{external_symbol[3:]}",
                    asset_type=AssetType.STOCK,
                )
            return None

        return Symbol(ticker=entry["ticker"], asset_type=entry["asset_type"])

    def map_to_prediction_market(
        self, external_symbol: str, markets: list
    ) -> Optional[str]:
        """
        Attempts to find a matching prediction market ticker for an external symbol.
        e.g. BTCUSD -> 'BTC-20260331-ABOVE-70000'
        """
        # This will be used in Task 5 extension for Kalshi/Poly matching
        return None
