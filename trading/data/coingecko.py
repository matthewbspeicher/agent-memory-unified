"""
CoinGecko async client.

Supports both the free public API and the Demo API key (x-cg-demo-api-key header).
Configure via ``Settings.coingecko_api_key`` or pass ``api_key`` directly.

Usage::

    client = CoinGeckoClient(api_key="CG-xxx")
    price = await client.get_price("bitcoin")
    chart = await client.get_market_chart("bitcoin", days=7)
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.coingecko.com/api/v3"

SYMBOL_TO_COINGECKO: dict[str, str] = {
    "BTCUSD": "bitcoin",
    "ETHUSD": "ethereum",
}


class CoinGeckoClient:
    """
    Lightweight async CoinGecko client.

    Args:
        api_key: CoinGecko Demo API key (``x-cg-demo-api-key`` header).
                 Pass ``None`` to use the unauthenticated free tier (rate-limited).
        timeout:  HTTP request timeout in seconds (default 10).
    """

    def __init__(self, api_key: str | None = None, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["x-cg-demo-api-key"] = self._api_key
        return headers

    async def get_price(self, coin_id: str) -> dict[str, Any]:
        """
        Return the current USD price and 24-hour change for ``coin_id``.

        Response shape (mirrors CoinGecko)::

            {
                "bitcoin": {
                    "usd": 65432.0,
                    "usd_24h_change": -1.23
                }
            }

        Raises ``httpx.HTTPStatusError`` on non-2xx responses.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{_BASE_URL}/simple/price",
                params={
                    "ids": coin_id,
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                },
                headers=self._headers(),
            )
            resp.raise_for_status()
        return resp.json()

    async def get_market_chart(self, coin_id: str, days: int | str) -> dict[str, Any]:
        """
        Return OHLC/price market chart data for ``coin_id`` over ``days`` days.

        Response shape (mirrors CoinGecko)::

            {
                "prices": [[timestamp_ms, price], ...],
                "market_caps": [[timestamp_ms, cap], ...],
                "total_volumes": [[timestamp_ms, volume], ...]
            }

        Args:
            coin_id: CoinGecko coin ID, e.g. ``"bitcoin"``, ``"ethereum"``.
            days:    Number of days of data to retrieve, or ``"max"`` for all history.

        Raises ``httpx.HTTPStatusError`` on non-2xx responses.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{_BASE_URL}/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": days},
                headers=self._headers(),
            )
            resp.raise_for_status()
        return resp.json()

    async def get_ohlc_closes(
        self,
        coin_id: str,
        count: int,
    ) -> list[float]:
        """Fetch approximate close prices via get_market_chart(days=1).

        Returns the last ``count`` ~5-minute samples from CoinGecko's market
        chart — not exact OHLC candles. Sufficient for the evaluator's
        ~8-hour lookback window.
        """
        chart = await self.get_market_chart(coin_id, days=1)
        prices = [p[1] for p in chart.get("prices", [])]
        return prices[-count:] if len(prices) >= count else prices
