from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.binance.com/api/v3"


class BinanceDataSource:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        resp = await self._client.get(
            f"{self.base_url}/ticker/price", params={"symbol": symbol}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
    ) -> list[list[Any]]:
        resp = await self._client.get(
            f"{self.base_url}/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_historical_bars(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        klines = await self.get_klines(symbol, interval, limit)
        bars = []
        for k in klines:
            bars.append(
                {
                    "timestamp": k[0],
                    "open": Decimal(str(k[1])),
                    "high": Decimal(str(k[2])),
                    "low": Decimal(str(k[3])),
                    "close": Decimal(str(k[4])),
                    "volume": Decimal(str(k[5])),
                }
            )
        return bars

    async def get_all_tickers(self) -> list[dict[str, Any]]:
        resp = await self._client.get(f"{self.base_url}/ticker/24hr")
        resp.raise_for_status()
        return resp.json()

    async def __aenter__(self) -> "BinanceDataSource":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
