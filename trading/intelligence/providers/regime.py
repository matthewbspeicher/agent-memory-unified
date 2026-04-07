from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider

if TYPE_CHECKING:
    from memory.regime import RegimeMemoryManager

logger = logging.getLogger(__name__)


class RegimeProvider(BaseIntelProvider):
    """Uses RegimeMemoryManager to provide historical regime context.

    Score is always 0 (regime doesn't dictate direction), but confidence
    increases when many similar historical regimes are found in memory.
    This acts as a conviction multiplier — familiar regimes get higher trust.
    """

    def __init__(self, memory_manager: RegimeMemoryManager | None = None):
        self.memory_manager = memory_manager

    @property
    def name(self) -> str:
        return "regime"

    async def analyze(self, symbol: str) -> IntelReport | None:
        if not self.memory_manager:
            return None

        try:
            bars = await self._fetch_bars(symbol)
            if not bars or len(bars) < 2:
                return None

            regime = self.memory_manager.detect_regime(bars)

            from broker.models import Symbol as SymbolModel
            memories = await self.memory_manager.recall_similar_regimes(
                SymbolModel(ticker=symbol), regime
            )

            # Conviction boost: more historical parallels = higher confidence
            confidence = min(0.5 + (len(memories) * 0.1), 1.0)

            # Store current regime for future recall (fire-and-forget)
            try:
                await self.memory_manager.store_regime(
                    SymbolModel(ticker=symbol),
                    regime,
                    {"volatility": self._calc_volatility(bars)},
                )
            except Exception:
                pass  # non-critical

            return IntelReport(
                source=self.name,
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                score=0.0,  # regime doesn't dictate direction
                confidence=confidence,
                veto=False,
                veto_reason=None,
                details={
                    "regime": regime,
                    "recalled_count": len(memories),
                },
            )
        except Exception as e:
            logger.warning("RegimeProvider failed for %s: %s", symbol, e)
            return None

    async def _fetch_bars(self, symbol: str) -> list:
        """Fetch recent price bars. Override in tests."""
        raise NotImplementedError("Requires DataBus or exchange API integration")

    @staticmethod
    def _calc_volatility(bars: list) -> float:
        prices = [float(b.close) for b in bars]
        if len(prices) < 2:
            return 0.0
        returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
        avg = sum(returns) / len(returns)
        return (sum((r - avg) ** 2 for r in returns) / len(returns)) ** 0.5
