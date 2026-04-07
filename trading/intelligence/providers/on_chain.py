from __future__ import annotations

import logging
from datetime import datetime, timezone

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider

logger = logging.getLogger(__name__)


class OnChainProvider(BaseIntelProvider):
    """Reads exchange netflow data to gauge accumulation vs distribution."""

    def __init__(self, coinglass_api_key: str | None = None):
        self.coinglass_api_key = coinglass_api_key

    @property
    def name(self) -> str:
        return "on_chain"

    async def analyze(self, symbol: str) -> IntelReport | None:
        try:
            netflow = await self._fetch_exchange_netflow(symbol)
            avg_30d = await self._fetch_exchange_netflow_30d_avg(symbol)
        except Exception as e:
            logger.warning("OnChainProvider failed for %s: %s", symbol, e)
            return None

        score = self._netflow_to_score(netflow, avg_30d)
        confidence = self._netflow_to_confidence(netflow, avg_30d)
        veto, veto_reason = self._check_veto(netflow, avg_30d)

        return IntelReport(
            source=self.name,
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            score=score,
            confidence=confidence,
            veto=veto,
            veto_reason=veto_reason,
            details={
                "exchange_netflow": netflow,
                "avg_30d_netflow": avg_30d,
            },
        )

    async def _fetch_exchange_netflow(self, symbol: str = "BTCUSD") -> float:
        """Fetch latest exchange netflow from CoinGlass API."""
        import aiohttp

        if not self.coinglass_api_key:
            raise ValueError("No CoinGlass API key configured")
        coin = symbol[:3]
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://open-api-v3.coinglass.com/api/indicator/exchange/netflow-total",
                params={"coin": coin, "range": "1d"},
                headers={"CG-API-KEY": self.coinglass_api_key},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
                return float(data.get("data", [{}])[-1].get("value", 0.0))

    async def _fetch_exchange_netflow_30d_avg(self, symbol: str = "BTCUSD") -> float:
        """Fetch 30-day average exchange netflow from CoinGlass API."""
        import aiohttp

        if not self.coinglass_api_key:
            raise ValueError("No CoinGlass API key configured")
        coin = symbol[:3]
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://open-api-v3.coinglass.com/api/indicator/exchange/netflow-total",
                params={"coin": coin, "range": "30d"},
                headers={"CG-API-KEY": self.coinglass_api_key},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
                values = [float(d.get("value", 0.0)) for d in data.get("data", [])]
                if not values:
                    return 0.0
                return sum(values) / len(values)

    @staticmethod
    def _netflow_to_score(netflow: float, avg_30d: float) -> float:
        """Convert netflow to a score between -1.0 and 1.0.

        Negative netflow (outflow from exchanges) = accumulation = bullish (positive score).
        Positive netflow (inflow to exchanges) = distribution = bearish (negative score).
        """
        if avg_30d == 0:
            return 0.0
        ratio = netflow / abs(avg_30d)
        clamped = max(-1.0, min(1.0, ratio))
        return -clamped * 0.5

    @staticmethod
    def _netflow_to_confidence(netflow: float, avg_30d: float) -> float:
        """Higher deviation from average = higher confidence in the signal."""
        if avg_30d == 0:
            return 0.3
        deviation = abs(netflow) / abs(avg_30d)
        return min(0.3 + deviation * 0.3, 1.0)

    @staticmethod
    def _check_veto(netflow: float, avg_30d: float) -> tuple[bool, str | None]:
        """Veto if exchange inflow exceeds 2x the 30-day average (panic selling risk)."""
        if avg_30d == 0:
            return False, None
        if netflow > 0 and netflow > abs(avg_30d) * 2.0:
            return True, f"Exchange inflow {netflow:.0f} exceeds 2x 30d avg ({abs(avg_30d):.0f})"
        return False, None
