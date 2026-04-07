from __future__ import annotations

import logging
from datetime import datetime, timezone

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider
from data.exchange_client import ExchangeClient

logger = logging.getLogger(__name__)


class AnomalyProvider(BaseIntelProvider):
    """Detects anomalies via volume deviation, price-volume divergence, spread widening."""

    def __init__(self):
        self._exchange = ExchangeClient()

    async def close(self):
        await self._exchange.close()

    @property
    def name(self) -> str:
        return "anomaly"

    async def analyze(self, symbol: str) -> IntelReport | None:
        try:
            volume_ratio = await self._fetch_volume_ratio(symbol)
            price_direction = await self._fetch_price_direction(symbol)
            spread_ratio = await self._fetch_spread_ratio(symbol)
        except Exception as e:
            logger.warning("AnomalyProvider failed for %s: %s", symbol, e)
            return None

        score = self._compute_score(volume_ratio, price_direction, spread_ratio)
        confidence = self._compute_confidence(volume_ratio, spread_ratio)
        veto, veto_reason = self._check_veto(volume_ratio, price_direction)

        return IntelReport(
            source=self.name,
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            score=score,
            confidence=confidence,
            veto=veto,
            veto_reason=veto_reason,
            details={
                "volume_ratio": volume_ratio,
                "price_direction": price_direction,
                "spread_ratio": spread_ratio,
            },
        )

    async def _fetch_volume_ratio(self, symbol: str) -> float:
        """Current volume / 20-period average volume. Override in tests."""
        try:
            ticker_map = {"BTCUSD": "BTC/USDT", "ETHUSD": "ETH/USDT", "SOLUSD": "SOL/USDT"}
            ccxt_symbol = ticker_map.get(symbol, symbol.replace("USD", "/USDT"))
            ohlcv = await self._exchange.exchange.fetch_ohlcv(ccxt_symbol, "1h", limit=21)
            if len(ohlcv) < 21:
                return 1.0
            volumes = [c[5] for c in ohlcv]
            avg_vol = sum(volumes[:-1]) / len(volumes[:-1])
            return volumes[-1] / avg_vol if avg_vol > 0 else 1.0
        except Exception as e:
            logger.warning(f"Error fetching volume ratio: {e}")
            return 1.0

    async def _fetch_price_direction(self, symbol: str) -> float:
        """Recent price movement: +1 = up, -1 = down, 0 = flat. Override in tests."""
        try:
            ticker_map = {"BTCUSD": "BTC/USDT", "ETHUSD": "ETH/USDT", "SOLUSD": "SOL/USDT"}
            ccxt_symbol = ticker_map.get(symbol, symbol.replace("USD", "/USDT"))
            ohlcv = await self._exchange.exchange.fetch_ohlcv(ccxt_symbol, "5m", limit=2)
            if len(ohlcv) < 2:
                return 0.0
            prev_close = ohlcv[-2][4]
            curr_close = ohlcv[-1][4]
            pct = (curr_close - prev_close) / prev_close
            if pct > 0.001:
                return 1.0
            elif pct < -0.001:
                return -1.0
            return 0.0
        except Exception as e:
            logger.warning(f"Error fetching price direction: {e}")
            return 0.0

    async def _fetch_spread_ratio(self, symbol: str) -> float:
        """Current spread / average spread. >1 = widening. Override in tests."""
        try:
            ticker_map = {"BTCUSD": "BTC/USDT", "ETHUSD": "ETH/USDT", "SOLUSD": "SOL/USDT"}
            ccxt_symbol = ticker_map.get(symbol, symbol.replace("USD", "/USDT"))
            orderbook = await self._exchange.exchange.fetch_order_book(ccxt_symbol, limit=5)
            if not orderbook["bids"] or not orderbook["asks"]:
                return 1.0
            spread = orderbook["asks"][0][0] - orderbook["bids"][0][0]
            mid = (orderbook["asks"][0][0] + orderbook["bids"][0][0]) / 2
            spread_bps = (spread / mid) * 10000 if mid > 0 else 0
            # Normal BTC spread is ~1-2 bps. Ratio > 2 = widening.
            return spread_bps / 1.5 if spread_bps > 0 else 1.0
        except Exception as e:
            logger.warning(f"Error fetching spread ratio: {e}")
            return 1.0

    @staticmethod
    def _compute_score(
        volume_ratio: float, price_direction: float, spread_ratio: float
    ) -> float:
        score = 0.0
        if volume_ratio >= 3.0:
            score += price_direction * 0.2
        elif volume_ratio >= 2.0:
            score += price_direction * 0.1
        if spread_ratio > 2.0:
            score -= 0.2
        elif spread_ratio > 1.5:
            score -= 0.1
        return max(-1.0, min(1.0, score))

    @staticmethod
    def _compute_confidence(volume_ratio: float, spread_ratio: float) -> float:
        volume_conf = (
            min((volume_ratio - 1.0) / 4.0, 0.5) if volume_ratio > 1.0 else 0.0
        )
        spread_conf = (
            min((spread_ratio - 1.0) / 2.0, 0.3) if spread_ratio > 1.0 else 0.0
        )
        return min(0.3 + volume_conf + spread_conf, 1.0)

    @staticmethod
    def _check_veto(
        volume_ratio: float, price_direction: float
    ) -> tuple[bool, str | None]:
        """Veto if volume > 5x normal AND price moving against (likely manipulation/black swan)."""
        if volume_ratio > 5.0 and price_direction < 0:
            return (
                True,
                f"Volume {volume_ratio:.1f}x normal with price declining — possible manipulation",
            )
        return False, None
