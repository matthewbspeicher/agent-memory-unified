# python/tests/unit/test_data/test_coingecko_closes.py
from __future__ import annotations
from unittest.mock import AsyncMock, patch

import pytest

from data.coingecko import CoinGeckoClient, SYMBOL_TO_COINGECKO


def test_symbol_mapping():
    assert SYMBOL_TO_COINGECKO["BTCUSD"] == "bitcoin"
    assert SYMBOL_TO_COINGECKO["ETHUSD"] == "ethereum"


async def test_get_ohlc_closes_extracts_last_n_prices():
    client = CoinGeckoClient(api_key="test-key")
    mock_chart = {
        "prices": [
            [1711612800000, 70000.0],
            [1711613100000, 70100.0],
            [1711613400000, 70200.0],
            [1711613700000, 70050.0],
            [1711614000000, 70150.0],
        ],
        "market_caps": [],
        "total_volumes": [],
    }
    with patch.object(client, "get_market_chart", new_callable=AsyncMock, return_value=mock_chart):
        closes = await client.get_ohlc_closes("bitcoin", count=3)

    assert len(closes) == 3
    assert closes == [70200.0, 70050.0, 70150.0]


async def test_get_ohlc_closes_truncates():
    client = CoinGeckoClient(api_key="test-key")
    mock_chart = {
        "prices": [[i * 300000, 100.0 + i] for i in range(200)],
        "market_caps": [],
        "total_volumes": [],
    }
    with patch.object(client, "get_market_chart", new_callable=AsyncMock, return_value=mock_chart):
        closes = await client.get_ohlc_closes("bitcoin", count=100)

    assert len(closes) == 100
    assert closes[0] == 200.0  # 100.0 + 100
    assert closes[-1] == 299.0  # 100.0 + 199


async def test_get_ohlc_closes_short_response():
    client = CoinGeckoClient(api_key="test-key")
    mock_chart = {
        "prices": [[1, 100.0], [2, 101.0]],
        "market_caps": [],
        "total_volumes": [],
    }
    with patch.object(client, "get_market_chart", new_callable=AsyncMock, return_value=mock_chart):
        closes = await client.get_ohlc_closes("bitcoin", count=100)

    # Fewer than requested — return what's available
    assert len(closes) == 2
    assert closes == [100.0, 101.0]
