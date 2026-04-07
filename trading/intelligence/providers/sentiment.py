from __future__ import annotations

import logging
from datetime import datetime, timezone

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider

logger = logging.getLogger(__name__)


class SentimentProvider(BaseIntelProvider):
    """Reads Crypto Fear & Greed Index from Alternative.me (free, no key).
    Optionally reads LunarCrush social volume and sentiment if API key is provided.
    """

    def __init__(self, lunarcrush_api_key: str | None = None):
        self.lunarcrush_api_key = lunarcrush_api_key

    @property
    def name(self) -> str:
        return "sentiment"

    async def analyze(self, symbol: str) -> IntelReport | None:
        try:
            fg_value = await self._fetch_fear_greed()
        except Exception as e:
            logger.warning("SentimentProvider (F&G) failed: %s", e)
            return None

        fg_score = self._fg_to_score(fg_value)
        confidence = self._fg_to_confidence(fg_value)
        
        details = {"fear_greed_value": fg_value}
        final_score = fg_score

        # Combine with LunarCrush if available
        if self.lunarcrush_api_key:
            try:
                lc_score, lc_conf, lc_details = await self._fetch_lunarcrush(symbol)
                final_score = (fg_score + lc_score) / 2
                confidence = max(confidence, lc_conf)
                details.update(lc_details)
            except Exception as e:
                logger.warning("SentimentProvider (LunarCrush) failed: %s", e)

        return IntelReport(
            source=self.name,
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            score=final_score,
            confidence=confidence,
            veto=False,
            veto_reason=None,
            details=details,
        )

    async def _fetch_lunarcrush(self, symbol: str) -> tuple[float, float, dict]:
        """Fetch LunarCrush AltRank/GalaxyScore and social volume for the coin."""
        import aiohttp
        
        # Strip 'USD' or 'USDT' from symbol to get the coin ticker
        coin = symbol.replace("USDT", "").replace("USD", "")
        if not coin:
            return 0.0, 0.0, {}

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.lunarcrush_api_key}"}
            async with session.get(
                f"https://lunarcrush.com/api4/public/coins/{coin}/v1",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                
                # LunarCrush AltRank: 1 is best, higher is worse
                # Galaxy Score: 0-100, 100 is best
                galaxy_score = float(data.get("data", {}).get("galaxy_score", 50.0))
                alt_rank = float(data.get("data", {}).get("alt_rank", 1000.0))
                
                # Convert Galaxy Score (0-100) to -1.0 to 1.0
                score = (galaxy_score - 50.0) / 50.0
                
                # High confidence if AltRank is top 100 or bottom 100
                conf = 0.5
                if alt_rank < 100:
                    conf = 0.8
                    score += 0.2 # Boost for top alt rank
                
                return max(-1.0, min(1.0, score)), conf, {
                    "lunarcrush_galaxy_score": galaxy_score,
                    "lunarcrush_alt_rank": alt_rank
                }

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
