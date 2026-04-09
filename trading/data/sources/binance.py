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


def calc_ema(closes: list[Decimal], period: int) -> Decimal:
    if len(closes) < period:
        return Decimal("0")
    multiplier = Decimal(2) / Decimal(period + 1)
    ema = sum(closes[:period]) / Decimal(period)
    for price in closes[period:]:
        ema = price * multiplier + ema * (Decimal(1) - multiplier)
    return ema


def calc_rsi(closes: list[Decimal], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = Decimal("0")
    losses = Decimal("0")
    for i in range(len(closes) - period, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / Decimal(period)
    avg_loss = losses / Decimal(period)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi = Decimal(100) - (Decimal(100) / (Decimal(1) + rs))
    return float(rsi)


def calc_vwap(candles: list[dict]) -> Decimal | None:
    if not candles:
        return None
    from datetime import datetime, timezone

    midnight = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    session_candles = [
        c for c in candles if c.get("timestamp", 0) >= int(midnight.timestamp() * 1000)
    ]
    if not session_candles:
        return None
    cum_tpv = Decimal("0")
    cum_vol = Decimal("0")
    for c in session_candles:
        typical_price = (c["high"] + c["low"] + c["close"]) / Decimal(3)
        cum_tpv += typical_price * c["volume"]
        cum_vol += c["volume"]
    return cum_tpv / cum_vol if cum_vol > 0 else None
