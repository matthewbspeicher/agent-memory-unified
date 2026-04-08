# trading/data/exchange_client.py
"""Unified CCXT exchange client with fallback and partial failure handling."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import ccxt.async_support as ccxt

from intelligence.circuit_breaker import ProviderCircuitBreaker

logger = logging.getLogger(__name__)


@dataclass
class FetchError:
    exchange: str
    data_type: str
    error: str


@dataclass
class FetchResult:
    ohlcv: list[dict] | None = None
    funding: dict | None = None
    oi: float | None = None
    orderbook: dict | None = None
    errors: list[FetchError] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_complete(self) -> bool:
        return all(
            v is not None for v in [self.ohlcv, self.funding, self.oi, self.orderbook]
        )

    @property
    def partial_success(self) -> bool:
        return any(
            v is not None for v in [self.ohlcv, self.funding, self.oi, self.orderbook]
        )

    @property
    def available_data_types(self) -> list[str]:
        types = []
        if self.ohlcv is not None:
            types.append("ohlcv")
        if self.funding is not None:
            types.append("funding")
        if self.oi is not None:
            types.append("oi")
        if self.orderbook is not None:
            types.append("orderbook")
        return types


class ExchangeClient:
    """Async CCXT wrapper with multi-exchange fallback and circuit breakers."""

    def __init__(
        self,
        primary: str = "binance",
        fallbacks: list[str] | None = None,
        enable_rate_limit: bool = True,
    ):
        self._exchange_ids = [primary] + (fallbacks or [])
        self._exchanges: dict[str, ccxt.Exchange] = {}
        self._breakers: dict[str, ProviderCircuitBreaker] = {}

        for eid in self._exchange_ids:
            exchange_class = getattr(ccxt, eid, None)
            if exchange_class:
                self._exchanges[eid] = exchange_class(
                    {"enableRateLimit": enable_rate_limit}
                )
                self._breakers[eid] = ProviderCircuitBreaker(
                    failure_threshold=5, reset_timeout=60
                )

    def _format_spot(self, symbol: str) -> str:
        return symbol.replace("USD", "/USDT")

    def _format_perp(self, symbol: str) -> str:
        return symbol.replace("USD", "/USDT:USDT")

    async def fetch_all(self, symbol: str) -> FetchResult:
        """Fetch all data types with exchange fallback."""
        result = FetchResult()
        for eid in self._exchange_ids:
            exchange = self._exchanges.get(eid)
            breaker = self._breakers.get(eid)
            if not exchange or not breaker:
                continue
            if breaker.state == "open" and not breaker._should_attempt_reset():
                continue

            try:
                if result.ohlcv is None:
                    result.ohlcv = await self._fetch_ohlcv(exchange, symbol)
            except Exception as e:
                result.errors.append(FetchError(eid, "ohlcv", str(e)))

            try:
                if result.funding is None:
                    result.funding = await self._fetch_funding(exchange, symbol)
            except Exception as e:
                result.errors.append(FetchError(eid, "funding", str(e)))

            try:
                if result.oi is None:
                    result.oi = await self._fetch_oi(exchange, symbol)
            except Exception as e:
                result.errors.append(FetchError(eid, "oi", str(e)))

            try:
                if result.orderbook is None:
                    result.orderbook = await self._fetch_orderbook(exchange, symbol)
            except Exception as e:
                result.errors.append(FetchError(eid, "orderbook", str(e)))

            if result.is_complete:
                break

        return result

    async def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """Backward-compat: fetch ticker from primary exchange."""
        exchange = next(iter(self._exchanges.values()), None)
        if not exchange:
            return {}
        try:
            return await exchange.fetch_ticker(self._format_spot(symbol))
        except Exception as e:
            logger.warning("fetch_ticker failed: %s", e)
            return {}

    async def fetch_funding_rate(self, symbol: str) -> float:
        """Backward-compat: fetch funding rate from primary exchange."""
        exchange = next(iter(self._exchanges.values()), None)
        if not exchange:
            return 0.0
        try:
            data = await exchange.fetch_funding_rate(self._format_perp(symbol))
            return data.get("fundingRate", 0.0)
        except Exception as e:
            logger.warning("fetch_funding_rate failed: %s", e)
            return 0.0

    async def _fetch_ohlcv(self, exchange: ccxt.Exchange, symbol: str) -> list[dict]:
        raw = await exchange.fetch_ohlcv(self._format_spot(symbol), "1m", limit=100)
        return [
            {
                "timestamp": r[0],
                "open": r[1],
                "high": r[2],
                "low": r[3],
                "close": r[4],
                "volume": r[5],
            }
            for r in raw
        ]

    async def _fetch_funding(self, exchange: ccxt.Exchange, symbol: str) -> dict:
        data = await exchange.fetch_funding_rate(self._format_perp(symbol))
        rate = data.get("fundingRate", 0.0)
        return {
            "rate": rate,
            "annualized": rate * 3 * 365,
            "timestamp": data.get("timestamp"),
        }

    async def _fetch_oi(self, exchange: ccxt.Exchange, symbol: str) -> float:
        try:
            data = await exchange.fetch_open_interest(self._format_perp(symbol))
            return float(data.get("openInterestAmount", 0) or 0)
        except (ccxt.NotSupported, AttributeError):
            return 0.0

    async def _fetch_orderbook(self, exchange: ccxt.Exchange, symbol: str) -> dict:
        book = await exchange.fetch_order_book(self._format_spot(symbol), limit=20)
        return {"bids": book.get("bids", [])[:20], "asks": book.get("asks", [])[:20]}

    async def close(self) -> None:
        for exchange in self._exchanges.values():
            await exchange.close()
