from __future__ import annotations

import logging
from datetime import datetime, timezone

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider
from memory.regime import RegimeMemoryManager

logger = logging.getLogger(__name__)


class RegimeProvider(BaseIntelProvider):
    """Uses RegimeMemoryManager to provide historical context and conviction boosts."""

    def __init__(self, memory_manager: RegimeMemoryManager | None = None):
        self.memory_manager = memory_manager

    @property
    def name(self) -> str:
        return "regime"

    async def analyze(self, symbol: str) -> IntelReport | None:
        if not self.memory_manager:
            return None

        try:
            import yfinance as yf
            from broker.models import Bar, Symbol, AssetType
            
            ticker_map = {"BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD"}
            yf_ticker = ticker_map.get(symbol, f"{symbol}=X")
            
            df = yf.download(yf_ticker, period="5d", interval="1h", progress=False)
            if df.empty:
                return None
                
            bars = []
            for ts, row in df.iterrows():
                bars.append(Bar(
                    symbol=Symbol(ticker=symbol, asset_type=AssetType.FOREX),
                    timestamp=ts.to_pydatetime().replace(tzinfo=timezone.utc),
                    close=row['Close']
                ))

            regime = self.memory_manager.detect_regime(bars)
            memories = await self.memory_manager.recall_similar_regimes(Symbol(ticker=symbol), regime, bars=bars)
            
            # Use SimilarityFilter to process neighbors
            from intelligence.similarity import SimilarityFilter
            sf = SimilarityFilter(min_neighbors=1)
            results = sf.process_neighbors(memories)
            
            # Conviction boost based on historical win rate
            adjustment = results.get("confidence_adjustment", 0.0)
            confidence = min(0.5 + adjustment + (len(memories) * 0.05), 1.0)

            return IntelReport(
                source=self.name,
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                score=0.0, # Regime doesn't dictate direction, only conviction
                confidence=confidence,
                veto=False,
                regime_context=regime,
                details={
                    "regime": regime,
                    "recalled_count": len(memories),
                    "memory_analysis": results.get("reasoning")
                },
            )
        except Exception as e:
            logger.warning("RegimeProvider failed for %s: %s", symbol, e)
            return None
