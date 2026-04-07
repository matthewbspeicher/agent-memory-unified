from __future__ import annotations
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional

from broker.models import Bar, Symbol
from adapters.remembr.client import AsyncRemembrClient
from memory.vector_service import MarketVectorService

logger = logging.getLogger(__name__)

class RegimeMemoryManager:
    """Manages market regime detection and persistence in Vector Memory."""

    def __init__(self, client: AsyncRemembrClient, vector_service: MarketVectorService | None = None):
        self.client = client
        self.vector_service = vector_service

    # HMM state labels (4-state model)
    _HMM_STATES = ["quiet_range", "trending_bull", "trending_bear", "volatile_range"]

    def detect_regime(self, bars: List[Bar]) -> str:
        """Detect market regime using HMM (4-state) with heuristic fallback.

        HMM observes 2 features: returns and volatility (rolling 5-bar std).
        Falls back to simple heuristic when hmmlearn is unavailable or
        insufficient data (<30 bars) for reliable HMM fitting.
        """
        if len(bars) < 2:
            return "unknown"

        prices = [float(b.close) for b in bars]
        returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]

        # Try HMM if we have enough data
        if len(returns) >= 30:
            try:
                return self._detect_regime_hmm(returns)
            except Exception as e:
                logger.debug("HMM regime detection failed, using heuristic: %s", e)

        return self._detect_regime_heuristic(returns)

    def _detect_regime_hmm(self, returns: List[float]) -> str:
        """4-state Gaussian HMM on (return, rolling_volatility) features."""
        import numpy as np
        from hmmlearn.hmm import GaussianHMM

        ret_arr = np.array(returns)
        # Rolling 5-period volatility as second feature
        window = min(5, len(ret_arr))
        vol = np.array([
            ret_arr[max(0, i - window + 1):i + 1].std()
            for i in range(len(ret_arr))
        ])

        X = np.column_stack([ret_arr, vol])

        model = GaussianHMM(
            n_components=4,
            covariance_type="diag",
            n_iter=50,
            random_state=42,
        )
        model.fit(X)

        # Get the most likely state for the last observation
        states = model.predict(X)
        current_state = states[-1]

        # Map HMM states to regime labels by their learned means
        # Sort states by (mean_return, mean_vol) to assign labels
        means = model.means_  # shape (4, 2): [return, vol]
        state_info = []
        for i in range(4):
            state_info.append((i, means[i][0], means[i][1]))

        # Assign labels based on return/vol characteristics
        # Sort by mean return ascending
        state_info.sort(key=lambda x: x[1])

        label_map = {}
        # Lowest return = trending_bear
        label_map[state_info[0][0]] = "trending_bear"
        # Highest return = trending_bull
        label_map[state_info[3][0]] = "trending_bull"
        # Of the two middle states, higher vol = volatile_range, lower = quiet_range
        mid_states = sorted(state_info[1:3], key=lambda x: x[2])
        label_map[mid_states[0][0]] = "quiet_range"
        label_map[mid_states[1][0]] = "volatile_range"

        return label_map.get(current_state, "unknown")

    @staticmethod
    def _detect_regime_heuristic(returns: List[float]) -> str:
        """Simple heuristic fallback for small datasets."""
        avg_return = sum(returns) / len(returns)
        volatility = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5

        is_trending = abs(avg_return) > 0.0005
        is_volatile = volatility > 0.005

        if is_trending:
            if avg_return > 0:
                return "trending_bull" if not is_volatile else "volatile_uptrend"
            else:
                return "trending_bear" if not is_volatile else "volatile_downtrend"
        else:
            return "quiet_range" if not is_volatile else "volatile_range"

    async def recall_similar_regimes(self, symbol: Symbol, regime: str, bars: List[Bar] | None = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for similar past regimes for this symbol using vector search if available."""
        if self.vector_service and bars:
            context_str = self.vector_service.create_context_string(symbol, bars)
            # We don't send the raw vector to search() yet because the client
            # usually handles the string-to-embedding internally or via the API.
            # But we've prepared the context_str specifically for high-fidelity matching.
            try:
                return await self.client.search(
                    query=context_str,
                    limit=limit,
                    tags=["regime", symbol.ticker]
                )
            except Exception as e:
                logger.warning("Vector search failed, falling back to keyword: %s", e)

        query = f"Regime: {regime}, Symbol: {symbol.ticker}"
        try:
            return await self.client.search(query, limit=limit, tags=["regime", symbol.ticker])
        except Exception as e:
            logger.warning("Failed to recall regimes: %s", e)
            return []

    async def store_regime(self, symbol: Symbol, regime: str, metrics: Dict[str, Any], bars: List[Bar] | None = None):
        """Store the current regime in memory, vectorizing if possible."""
        now = datetime.now(timezone.utc).isoformat()
        
        context_str = ""
        if self.vector_service and bars:
            context_str = self.vector_service.create_context_string(symbol, bars)
        
        value = f"Regime: {regime}, Symbol: {symbol.ticker}, Time: {now}, Vol: {metrics.get('volatility', 0):.4f}. {context_str}"
        
        try:
            await self.client.store(
                value=value,
                visibility="private",
                metadata={
                    "regime": regime,
                    "symbol": symbol.ticker,
                    "metrics": metrics,
                    "type": "market_regime",
                    "context": context_str
                },
                tags=["regime", symbol.ticker, regime]
            )
            logger.info("Stored market regime: %s for %s", regime, symbol.ticker)
        except Exception as e:
            logger.warning("Failed to store regime memory: %s", e)
