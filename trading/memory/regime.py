from __future__ import annotations
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional

from broker.models import Bar, Symbol
from adapters.remembr.client import AsyncRemembrClient  # Assuming it's in adapters

logger = logging.getLogger(__name__)


class RegimeMemoryManager:
    """Manages market regime detection and persistence in Vector Memory."""

    def __init__(self, client: AsyncRemembrClient):
        self.client = client

    def detect_regime(self, bars: List[Bar]) -> str:
        """Simple regime detection based on returns and volatility."""
        if len(bars) < 2:
            return "unknown"

        prices = [float(b.close) for b in bars]
        returns = [
            (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))
        ]
        avg_return = sum(returns) / len(returns)
        volatility = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5

        # Simple heuristic thresholds
        is_trending = abs(avg_return) > 0.0005  # 5bps avg per bar
        is_volatile = volatility > 0.005  # 50bps std dev

        if is_trending:
            if avg_return > 0:
                return "trending_bull" if not is_volatile else "volatile_uptrend"
            else:
                return "trending_bear" if not is_volatile else "volatile_downtrend"
        else:
            return "quiet_range" if not is_volatile else "volatile_range"

    async def recall_similar_regimes(
        self, symbol: Symbol, regime: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for similar past regimes for this symbol."""
        query = f"Regime: {regime}, Symbol: {symbol.ticker}"
        try:
            return await self.client.search(
                query, limit=limit, tags=["regime", symbol.ticker]
            )
        except Exception as e:
            logger.warning("Failed to recall regimes: %s", e)
            return []

    async def store_regime(self, symbol: Symbol, regime: str, metrics: Dict[str, Any]):
        """Store the current regime in memory."""
        now = datetime.now(timezone.utc).isoformat()
        value = f"Regime: {regime}, Symbol: {symbol.ticker}, Time: {now}, Vol: {metrics.get('volatility', 0):.4f}"

        try:
            await self.client.store(
                value=value,
                visibility="private",
                metadata={
                    "regime": regime,
                    "symbol": symbol.ticker,
                    "metrics": metrics,
                    "type": "market_regime",
                },
                tags=["regime", symbol.ticker, regime],
            )
            logger.info("Stored market regime: %s for %s", regime, symbol.ticker)
        except Exception as e:
            logger.warning("Failed to store regime memory: %s", e)
