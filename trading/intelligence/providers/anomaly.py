from __future__ import annotations

import logging
from datetime import datetime, timezone

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider

logger = logging.getLogger(__name__)


class AnomalyProvider(BaseIntelProvider):
    """Detects anomalies via volume deviation, price-volume divergence, spread widening."""

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
        raise NotImplementedError("Requires exchange API integration")

    async def _fetch_price_direction(self, symbol: str) -> float:
        """Recent price movement: +1 = up, -1 = down, 0 = flat. Override in tests."""
        raise NotImplementedError("Requires exchange API integration")

    async def _fetch_spread_ratio(self, symbol: str) -> float:
        """Current spread / average spread. >1 = widening. Override in tests."""
        raise NotImplementedError("Requires exchange API integration")

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
