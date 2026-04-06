"""Tests for CoinGeckoClient (Task 5)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from data.coingecko import CoinGeckoClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(json_data: dict, status_code: int = 200):
    """Return a context-manager mock httpx.AsyncClient that yields one response."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = json_data

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def test_init_stores_api_key():
    client = CoinGeckoClient(api_key="CG-test")
    assert client._api_key == "CG-test"


def test_init_default_key_is_none():
    client = CoinGeckoClient()
    assert client._api_key is None


def test_headers_include_demo_key_when_set():
    client = CoinGeckoClient(api_key="CG-abc")
    headers = client._headers()
    assert headers["x-cg-demo-api-key"] == "CG-abc"


def test_headers_no_demo_key_when_none():
    client = CoinGeckoClient()
    headers = client._headers()
    assert "x-cg-demo-api-key" not in headers


# ---------------------------------------------------------------------------
# get_price
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_price_returns_parsed_json():
    payload = {"bitcoin": {"usd": 65000.0, "usd_24h_change": -1.5}}
    mock_client = _make_mock_client(payload)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await CoinGeckoClient(api_key="CG-key").get_price("bitcoin")

    assert result == payload


@pytest.mark.asyncio
async def test_get_price_calls_correct_endpoint():
    payload = {"bitcoin": {"usd": 65000.0, "usd_24h_change": 0.5}}
    mock_client = _make_mock_client(payload)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await CoinGeckoClient(api_key="CG-key").get_price("bitcoin")

    mock_client.get.assert_awaited_once()
    call_args = mock_client.get.call_args
    url = call_args[0][0]
    assert "simple/price" in url
    params = call_args[1]["params"]
    assert params["ids"] == "bitcoin"
    assert params["vs_currencies"] == "usd"
    assert params["include_24hr_change"] == "true"


@pytest.mark.asyncio
async def test_get_price_sends_api_key_header():
    payload = {"ethereum": {"usd": 3000.0, "usd_24h_change": 2.0}}
    mock_client = _make_mock_client(payload)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await CoinGeckoClient(api_key="CG-xyz").get_price("ethereum")

    headers = mock_client.get.call_args[1]["headers"]
    assert headers["x-cg-demo-api-key"] == "CG-xyz"


@pytest.mark.asyncio
async def test_get_price_no_key_omits_header():
    payload = {"bitcoin": {"usd": 65000.0, "usd_24h_change": 0.0}}
    mock_client = _make_mock_client(payload)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await CoinGeckoClient().get_price("bitcoin")

    headers = mock_client.get.call_args[1]["headers"]
    assert "x-cg-demo-api-key" not in headers


# ---------------------------------------------------------------------------
# get_market_chart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_market_chart_returns_parsed_json():
    payload = {
        "prices": [[1710000000000, 65000.0]],
        "market_caps": [[1710000000000, 1_300_000_000_000.0]],
        "total_volumes": [[1710000000000, 30_000_000_000.0]],
    }
    mock_client = _make_mock_client(payload)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await CoinGeckoClient(api_key="CG-key").get_market_chart(
            "bitcoin", days=7
        )

    assert result == payload
    assert "prices" in result


@pytest.mark.asyncio
async def test_get_market_chart_calls_correct_endpoint():
    payload = {"prices": [], "market_caps": [], "total_volumes": []}
    mock_client = _make_mock_client(payload)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await CoinGeckoClient(api_key="CG-key").get_market_chart("ethereum", days=30)

    call_args = mock_client.get.call_args
    url = call_args[0][0]
    assert "ethereum/market_chart" in url
    params = call_args[1]["params"]
    assert params["vs_currency"] == "usd"
    assert params["days"] == 30


@pytest.mark.asyncio
async def test_get_market_chart_accepts_max_string():
    payload = {"prices": [], "market_caps": [], "total_volumes": []}
    mock_client = _make_mock_client(payload)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await CoinGeckoClient().get_market_chart("bitcoin", days="max")

    params = mock_client.get.call_args[1]["params"]
    assert params["days"] == "max"
