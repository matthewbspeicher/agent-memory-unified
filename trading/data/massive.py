"""
Massive.com market data async HTTP client.

Massive.com provides a Polygon.io-compatible REST API for market data.
Auth: query-param ``?apiKey={key}``.

Base URL: https://api.massive.com

Usage::

    client = MassiveClient(api_key="your-key")
    bars = await client.get_bars("AAPL", 1, "day", "2024-01-01", "2024-03-01")
    await client.close()
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.massive.com"


class MassiveClient:
    """
    Async Massive.com REST client (Polygon.io-compatible API).

    Args:
        api_key: Massive.com API key appended as ``?apiKey=`` on every request.
        timeout: HTTP request timeout in seconds (default 30).
    """

    BASE_URL = _BASE_URL

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._key = api_key
        self._client = httpx.AsyncClient(timeout=timeout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Merge caller params with the mandatory apiKey param."""
        p: dict[str, Any] = {"apiKey": self._key}
        if extra:
            p.update(extra)
        return p

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Perform a single GET and return the parsed JSON dict."""
        resp = await self._client.get(
            f"{self.BASE_URL}{path}",
            params=self._params(params),
        )
        resp.raise_for_status()
        return resp.json()

    async def _get_paginated(
        self, path: str, result_key: str, params: dict[str, Any] | None = None
    ) -> list[dict]:
        """
        Fetch all pages of a paginated endpoint.

        Massive uses the ``next_url`` field for cursor-based pagination.
        Each page's ``result_key`` list is concatenated and returned.
        """
        all_results: list[dict] = []
        data = await self._get(path, params)
        all_results.extend(data.get(result_key) or [])

        while data.get("next_url"):
            # next_url is a fully-qualified URL; we call it directly, only
            # appending our apiKey since it may already have other params.
            resp = await self._client.get(
                data["next_url"],
                params={"apiKey": self._key},
            )
            resp.raise_for_status()
            data = resp.json()
            all_results.extend(data.get(result_key) or [])

        return all_results

    # ------------------------------------------------------------------
    # Market data — bars / OHLCV
    # ------------------------------------------------------------------

    async def get_bars(
        self,
        ticker: str,
        multiplier: int,
        timespan: str,
        from_date: str,
        to_date: str,
        adjusted: bool = True,
        sort: str = "asc",
        limit: int = 5000,
    ) -> list[dict]:
        """
        Aggregate bars (OHLCV) for a ticker over a date range.

        GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}

        Args:
            ticker:     Uppercase ticker symbol, e.g. ``"AAPL"``.
            multiplier: Size of the timespan multiplier, e.g. ``1``.
            timespan:   ``"minute"``, ``"hour"``, ``"day"``, ``"week"``, ``"month"``.
            from_date:  Start date ``"YYYY-MM-DD"`` or millisecond timestamp.
            to_date:    End date ``"YYYY-MM-DD"`` or millisecond timestamp.
            adjusted:   Whether results are adjusted for splits (default True).
            sort:       ``"asc"`` or ``"desc"`` (default ``"asc"``).
            limit:      Max results per page (default 5000).

        Returns list of raw aggregate dicts with keys:
            ``v`` (volume), ``vw`` (VWAP), ``o`` (open), ``c`` (close),
            ``h`` (high), ``l`` (low), ``t`` (timestamp ms), ``n`` (trades).
        """
        path = f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        params: dict[str, Any] = {
            "adjusted": str(adjusted).lower(),
            "sort": sort,
            "limit": limit,
        }
        return await self._get_paginated(path, "results", params)

    # ------------------------------------------------------------------
    # Quotes / snapshots
    # ------------------------------------------------------------------

    async def get_quote(self, ticker: str) -> dict:
        """
        Latest NBBO quote for a single ticker.

        GET /v2/last/nbbo/{ticker}
        """
        data = await self._get(f"/v2/last/nbbo/{ticker}")
        return data.get("results", data)

    async def get_snapshot(self, ticker: str) -> dict:
        """
        Full snapshot (quote + last trade + day stats) for a single ticker.

        GET /v2/snapshot/locale/us/markets/stocks/tickers/{ticker}
        """
        data = await self._get(
            f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
        )
        return data.get("ticker", data)

    async def get_market_snapshot(self) -> list[dict]:
        """
        Snapshot for all tickers in the market.

        GET /v2/snapshot/locale/us/markets/stocks/tickers
        """
        return await self._get_paginated(
            "/v2/snapshot/locale/us/markets/stocks/tickers", "tickers"
        )

    async def get_top_movers(self, direction: str = "gainers") -> list[dict]:
        """
        Top gainers or losers for the current session.

        GET /v2/snapshot/locale/us/markets/stocks/{direction}

        Args:
            direction: ``"gainers"`` or ``"losers"`` (default ``"gainers"``).
        """
        data = await self._get(f"/v2/snapshot/locale/us/markets/stocks/{direction}")
        return data.get("tickers", [])

    # ------------------------------------------------------------------
    # Technical indicators
    # ------------------------------------------------------------------

    async def get_rsi(
        self,
        ticker: str,
        timespan: str = "day",
        window: int = 14,
        series_type: str = "close",
    ) -> dict:
        """
        Pre-computed RSI for a ticker.

        GET /v1/indicators/rsi/{ticker}
        """
        params: dict[str, Any] = {
            "timespan": timespan,
            "window": window,
            "series_type": series_type,
            "order": "desc",
            "limit": 1,
        }
        data = await self._get(f"/v1/indicators/rsi/{ticker}", params)
        return data.get("results", data)

    async def get_macd(
        self,
        ticker: str,
        timespan: str = "day",
        short_window: int = 12,
        long_window: int = 26,
        signal_window: int = 9,
        series_type: str = "close",
    ) -> dict:
        """
        Pre-computed MACD for a ticker.

        GET /v1/indicators/macd/{ticker}
        """
        params: dict[str, Any] = {
            "timespan": timespan,
            "short_window": short_window,
            "long_window": long_window,
            "signal_window": signal_window,
            "series_type": series_type,
            "order": "desc",
            "limit": 1,
        }
        data = await self._get(f"/v1/indicators/macd/{ticker}", params)
        return data.get("results", data)

    # ------------------------------------------------------------------
    # Economic / macro data
    # ------------------------------------------------------------------

    async def get_economic_data(self, indicator: str) -> dict:
        """
        Macro / economic time-series data.

        GET /fed/v1/{indicator}

        Common indicators: ``"treasury-yields"``, ``"inflation"``.
        """
        data = await self._get(f"/fed/v1/{indicator}")
        return data.get("results", data)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying httpx client and release connections."""
        await self._client.aclose()
