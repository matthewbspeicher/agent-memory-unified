"""DerivativesProvider -- funding rates + open interest as contrarian/confirmation signals.

Funding rates and open interest changes are strong short-term signals:
- **High positive funding** (longs pay shorts): overleveraged long -> bearish contrarian signal
- **High negative funding**: overleveraged short -> bullish contrarian signal
- **OI rising + price rising**: confirms trend (new money entering)
- **OI falling + price rising**: bearish divergence (short covering, not real buying)
- **OI rising + price falling**: new shorts entering -> bearish
- **OI falling + price falling**: capitulation, may reverse -> slight bullish
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider
from data.exchange_client import ExchangeClient

logger = logging.getLogger(__name__)

# Symbol mapping: internal names -> CCXT perpetual futures format
_PERP_SYMBOL_MAP: dict[str, str] = {
    "BTCUSD": "BTC/USDT:USDT",
    "ETHUSD": "ETH/USDT:USDT",
    "SOLUSD": "SOL/USDT:USDT",
    "BNBUSD": "BNB/USDT:USDT",
    "XRPUSD": "XRP/USDT:USDT",
    "DOGEUSD": "DOGE/USDT:USDT",
    "AVAXUSD": "AVAX/USDT:USDT",
    "ADAUSD": "ADA/USDT:USDT",
}

# Funding rate thresholds (per 8h period)
_FUNDING_HIGH = 0.0005  # 0.05% per 8h (~55% annualized)
_FUNDING_MODERATE = 0.0001  # 0.01% per 8h (~11% annualized)


class DerivativesProvider(BaseIntelProvider):
    """Funding rates + open interest as contrarian/confirmation signals."""

    def __init__(self, exchange_id: str = "binance") -> None:
        self._exchange = ExchangeClient(primary=exchange_id)

    async def close(self):
        await self._exchange.close()

    @property
    def name(self) -> str:
        return "derivatives"

    async def analyze(self, symbol: str) -> IntelReport | None:
        try:
            funding_rate = await self._fetch_funding_rate(symbol)
            oi_change_pct = await self._fetch_oi_change_pct(symbol)
            price_change_pct = await self._fetch_price_change_pct(symbol)
        except Exception as e:
            logger.warning(
                "DerivativesProvider: failed to fetch data for %s: %s", symbol, e
            )
            return None

        score = self._compute_score(funding_rate, oi_change_pct, price_change_pct)
        confidence = self._compute_confidence(funding_rate)

        return IntelReport(
            source=self.name,
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            score=score,
            confidence=confidence,
            veto=False,  # Informational signal, never vetoes
            veto_reason=None,
            details={
                "funding_rate": funding_rate,
                "oi_change_pct": oi_change_pct,
                "price_change_pct": price_change_pct,
            },
        )

    @staticmethod
    def _compute_score(
        funding_rate: float, oi_change_pct: float, price_change_pct: float
    ) -> float:
        """Compute combined score from funding rate and OI/price signals.

        Funding rate component (contrarian):
        - rate > 0.05%: score -= 0.3 (overleveraged longs)
        - rate > 0.01%: score -= 0.1
        - rate < -0.05%: score += 0.3 (overleveraged shorts)
        - rate < -0.01%: score += 0.1

        OI component (confirmation/divergence):
        - OI up + price up: score += 0.15 (confirming trend)
        - OI up + price down: score -= 0.15 (bearish new shorts)
        - OI down + price up: score -= 0.10 (short covering, not real demand)
        - OI down + price down: score += 0.10 (capitulation, may reverse)
        """
        score = 0.0

        # --- Funding rate component (contrarian) ---
        abs_funding = abs(funding_rate)
        if abs_funding > _FUNDING_HIGH:
            # Strong contrarian signal
            funding_contribution = -0.3 if funding_rate > 0 else 0.3
        elif abs_funding > _FUNDING_MODERATE:
            # Moderate contrarian signal
            funding_contribution = -0.1 if funding_rate > 0 else 0.1
        else:
            funding_contribution = 0.0

        score += funding_contribution

        # --- OI component (confirmation/divergence) ---
        oi_up = oi_change_pct > 0
        oi_down = oi_change_pct < 0
        price_up = price_change_pct > 0
        price_down = price_change_pct < 0

        if oi_up and price_up:
            score += 0.15  # Confirms uptrend
        elif oi_up and price_down:
            score -= 0.15  # Bearish new shorts
        elif oi_down and price_up:
            score -= 0.10  # Short covering, not real demand
        elif oi_down and price_down:
            score += 0.10  # Capitulation, may reverse

        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, score))

    @staticmethod
    def _compute_confidence(funding_rate: float) -> float:
        """Confidence scales with funding rate magnitude.

        Base: 0.5, scales up to 0.9 at extreme funding rates.
        """
        abs_funding = abs(funding_rate)
        # Scale: 0.5 base, up to 0.9 at extreme rates (>= 0.001 = 0.1%)
        # Linear interpolation from 0.5 at rate=0 to 0.9 at rate=0.001
        confidence = 0.5 + min(abs_funding / 0.001, 1.0) * 0.4
        return min(confidence, 0.9)

    async def _fetch_funding_rate(self, symbol: str) -> float:
        """Fetch current funding rate from exchange via CCXT."""
        ccxt_symbol = _PERP_SYMBOL_MAP.get(symbol, f"{symbol[:3]}/USDT:USDT")
        exchange = next(iter(self._exchange._exchanges.values()), None)
        if exchange is None:
            return 0.0
        try:
            funding = await exchange.fetch_funding_rate(ccxt_symbol)
            return funding.get("fundingRate", 0.0) or 0.0
        except Exception as e:
            logger.warning(
                f"DerivativesProvider failed to fetch funding rate for {symbol}: {e}"
            )
            return 0.0

    async def _fetch_oi_change_pct(self, symbol: str) -> float:
        """Fetch OI change % over recent period via CCXT.

        Returns percentage change in open interest.
        """
        ccxt_symbol = _PERP_SYMBOL_MAP.get(symbol, f"{symbol[:3]}/USDT:USDT")
        exchange = next(iter(self._exchange._exchanges.values()), None)
        if exchange is None:
            return 0.0
        try:
            # Fetch open interest history (last 2 periods)
            oi_data = await exchange.fetch_open_interest_history(
                ccxt_symbol, timeframe="1h", limit=2
            )
            if len(oi_data) < 2:
                return 0.0
            prev_oi = oi_data[0].get("openInterestValue", 0) or 0
            curr_oi = oi_data[1].get("openInterestValue", 0) or 0
            if prev_oi == 0:
                return 0.0
            return ((curr_oi - prev_oi) / prev_oi) * 100
        except Exception as e:
            logger.warning(
                f"DerivativesProvider failed to fetch OI change for {symbol}: {e}"
            )
            return 0.0

    async def _fetch_price_change_pct(self, symbol: str) -> float:
        """Fetch price change % over recent period via CCXT."""
        ccxt_symbol = _PERP_SYMBOL_MAP.get(symbol, f"{symbol[:3]}/USDT:USDT")
        exchange = next(iter(self._exchange._exchanges.values()), None)
        if exchange is None:
            return 0.0
        try:
            ticker = await exchange.fetch_ticker(ccxt_symbol)
            return ticker.get("percentage", 0.0) or 0.0
        except Exception as e:
            logger.warning(
                f"DerivativesProvider failed to fetch price change for {symbol}: {e}"
            )
            return 0.0
