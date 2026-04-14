"""Unit tests for the Alpha Vantage MCP server functions.

Tests the data-fetching helpers directly — fastmcp is a separate optional
dep and the FastMCP wiring is trivial glue, so we focus coverage on the
parsing/classification logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_servers.alphavantage import server


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_KEY", "TEST_KEY")


def _mock_session_with(payload: dict):
    """Build an AsyncMock replacement for ``aiohttp.ClientSession()``."""
    resp = MagicMock()
    resp.json = AsyncMock(return_value=payload)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


@pytest.mark.asyncio
async def test_sentiment_averages_feed_scores():
    payload = {
        "feed": [
            {"overall_sentiment_score": 0.40},
            {"overall_sentiment_score": 0.50},
            {"overall_sentiment_score": 0.60},
        ]
    }
    with patch("aiohttp.ClientSession", return_value=_mock_session_with(payload)):
        result = await server.fetch_market_sentiment("AAPL")

    assert result["ticker"] == "AAPL"
    assert result["score"] == pytest.approx(0.50)
    assert result["label"] == "Bullish"
    assert result["article_count"] == 3


@pytest.mark.asyncio
async def test_sentiment_empty_feed_returns_neutral():
    with patch("aiohttp.ClientSession", return_value=_mock_session_with({"feed": []})):
        result = await server.fetch_market_sentiment("XYZ")

    assert result == {
        "ticker": "XYZ",
        "score": 0.0,
        "label": "Neutral",
        "article_count": 0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "avg,expected_label",
    [
        (-0.50, "Bearish"),
        (-0.25, "Somewhat-Bearish"),
        (0.0, "Neutral"),
        (0.20, "Somewhat-Bullish"),
        (0.45, "Bullish"),
    ],
)
async def test_sentiment_label_bands(avg, expected_label):
    payload = {"feed": [{"overall_sentiment_score": avg}]}
    with patch("aiohttp.ClientSession", return_value=_mock_session_with(payload)):
        result = await server.fetch_market_sentiment("T")
    assert result["label"] == expected_label


@pytest.mark.asyncio
async def test_sentiment_raises_on_api_error():
    payload = {"Error Message": "Invalid API call"}
    with patch("aiohttp.ClientSession", return_value=_mock_session_with(payload)):
        with pytest.raises(server.AlphaVantageError, match="Invalid API call"):
            await server.fetch_market_sentiment("BAD")


@pytest.mark.asyncio
async def test_sentiment_raises_on_rate_limit():
    payload = {"Note": "Thank you for using Alpha Vantage! Our standard API..."}
    with patch("aiohttp.ClientSession", return_value=_mock_session_with(payload)):
        with pytest.raises(server.AlphaVantageError, match="rate limit"):
            await server.fetch_market_sentiment("AAPL")


@pytest.mark.asyncio
async def test_global_quote_parses_response():
    payload = {
        "Global Quote": {
            "05. price": "195.37",
            "09. change": "1.23",
            "10. change percent": "0.63%",
            "06. volume": "52134212",
        }
    }
    with patch("aiohttp.ClientSession", return_value=_mock_session_with(payload)):
        result = await server.fetch_global_quote("AAPL")

    assert result == {
        "ticker": "AAPL",
        "price": 195.37,
        "change": 1.23,
        "change_percent": "0.63%",
        "volume": 52134212,
    }


@pytest.mark.asyncio
async def test_global_quote_raises_when_empty():
    with patch(
        "aiohttp.ClientSession",
        return_value=_mock_session_with({"Global Quote": {}}),
    ):
        with pytest.raises(server.AlphaVantageError, match="No quote"):
            await server.fetch_global_quote("ZZZZ")


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("ALPHA_VANTAGE_KEY", raising=False)
    with pytest.raises(server.AlphaVantageError, match="ALPHA_VANTAGE_KEY"):
        server._api_key()
