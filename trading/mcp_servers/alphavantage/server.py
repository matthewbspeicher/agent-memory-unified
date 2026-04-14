"""Alpha Vantage MCP server.

Exposes Alpha Vantage market data to LLM agents via the Model Context
Protocol. Runs as a standalone process — install with the ``mcp`` extra:

    pip install -e "trading[mcp]"

Run with:

    ALPHA_VANTAGE_KEY=... python -m mcp_servers.alphavantage.server
"""

from __future__ import annotations

import os
from typing import Any

import aiohttp


_AV_BASE = "https://www.alphavantage.co/query"
_REQUEST_TIMEOUT_S = 10


class AlphaVantageError(RuntimeError):
    """Raised when the Alpha Vantage API returns an error or no data."""


def _api_key() -> str:
    key = os.getenv("ALPHA_VANTAGE_KEY")
    if not key:
        raise AlphaVantageError(
            "ALPHA_VANTAGE_KEY environment variable not set"
        )
    return key


async def _fetch(session: aiohttp.ClientSession, params: dict[str, str]) -> dict[str, Any]:
    params = {**params, "apikey": _api_key()}
    async with session.get(
        _AV_BASE,
        params=params,
        timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S),
    ) as resp:
        data = await resp.json()
    if "Error Message" in data:
        raise AlphaVantageError(data["Error Message"])
    if "Note" in data:
        raise AlphaVantageError(f"Alpha Vantage rate limit: {data['Note']}")
    return data


async def fetch_market_sentiment(ticker: str) -> dict[str, Any]:
    """Fetch AI-powered news sentiment for a ticker.

    Returns a structured dict: ``{ticker, score, label, article_count}``.
    Kept separate from the MCP tool registration so it's unit-testable
    without loading fastmcp.
    """
    async with aiohttp.ClientSession() as session:
        data = await _fetch(
            session,
            {"function": "NEWS_SENTIMENT", "tickers": ticker},
        )
    feed = data.get("feed") or []
    if not feed:
        return {
            "ticker": ticker,
            "score": 0.0,
            "label": "Neutral",
            "article_count": 0,
        }

    scores = [
        float(a.get("overall_sentiment_score", 0.0))
        for a in feed
        if "overall_sentiment_score" in a
    ]
    avg = sum(scores) / len(scores) if scores else 0.0
    # Alpha Vantage uses -1.0..1.0 with documented label bands.
    if avg <= -0.35:
        label = "Bearish"
    elif avg <= -0.15:
        label = "Somewhat-Bearish"
    elif avg < 0.15:
        label = "Neutral"
    elif avg < 0.35:
        label = "Somewhat-Bullish"
    else:
        label = "Bullish"

    return {
        "ticker": ticker,
        "score": round(avg, 4),
        "label": label,
        "article_count": len(feed),
    }


async def fetch_global_quote(ticker: str) -> dict[str, Any]:
    """Fetch real-time quote (latest price + change)."""
    async with aiohttp.ClientSession() as session:
        data = await _fetch(
            session,
            {"function": "GLOBAL_QUOTE", "symbol": ticker},
        )
    quote = data.get("Global Quote") or {}
    if not quote:
        raise AlphaVantageError(f"No quote returned for {ticker}")
    return {
        "ticker": ticker,
        "price": float(quote.get("05. price", 0.0)),
        "change": float(quote.get("09. change", 0.0)),
        "change_percent": quote.get("10. change percent", "0%"),
        "volume": int(float(quote.get("06. volume", 0))),
    }


def build_server():  # pragma: no cover - exercised only when fastmcp is installed
    """Construct the FastMCP server. Lazy import so unit tests don't need fastmcp."""
    from fastmcp import FastMCP

    mcp = FastMCP("AlphaVantage")

    @mcp.tool()
    async def get_market_sentiment(ticker: str) -> dict[str, Any]:
        """AI-powered news sentiment score for a ticker.

        Returns score in [-1.0, 1.0] with a human label and article count.
        """
        return await fetch_market_sentiment(ticker)

    @mcp.tool()
    async def get_global_quote(ticker: str) -> dict[str, Any]:
        """Real-time quote: latest price, change, volume."""
        return await fetch_global_quote(ticker)

    return mcp


def main() -> None:  # pragma: no cover
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
