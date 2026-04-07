from __future__ import annotations

import logging
from datetime import datetime, timezone

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider

logger = logging.getLogger(__name__)


class SentimentProvider(BaseIntelProvider):
    """Reads Crypto Fear & Greed Index from Alternative.me (free, no key)."""

    @property
    def name(self) -> str:
        return "sentiment"

    async def analyze(self, symbol: str) -> IntelReport | None:
        try:
            fg_value = await self._fetch_fear_greed()
        except Exception as e:
            logger.warning("SentimentProvider failed: %s", e)
            return None

        score = self._fg_to_score(fg_value)
        confidence = self._fg_to_confidence(fg_value)

        return IntelReport(
            source=self.name,
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            score=score,
            confidence=confidence,
            veto=False,
            veto_reason=None,
            details={"fear_greed_value": fg_value},
        )

    async def _fetch_fear_greed(self) -> int:
        """Fetch current Fear & Greed Index."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.alternative.me/fng/?limit=1",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
                return int(data["data"][0]["value"])

    @staticmethod
    def _fg_to_score(value: int) -> float:
        """Convert Fear & Greed (0-100) to score (-1 to +1), contrarian.

        Extreme fear (0-25) -> bullish (+0.2 to +0.5)
        Neutral (25-75) -> near zero
        Extreme greed (75-100) -> bearish (-0.2 to -0.5)
        """
        # Linear mapping: 0 -> +0.5, 50 -> 0.0, 100 -> -0.5
        return (50 - value) / 100.0

    @staticmethod
    def _fg_to_confidence(value: int) -> float:
        """Confidence is higher at extremes, lower near neutral."""
        distance_from_center = abs(value - 50)
        # 0 at center, 1.0 at extremes
        return min(distance_from_center / 50.0, 1.0) * 0.7 + 0.3
