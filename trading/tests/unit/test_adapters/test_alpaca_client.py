from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
import json

import pytest

from adapters.alpaca.errors import AlpacaRateLimited, AlpacaForbidden


async def test_get_account():
    from adapters.alpaca.client import AlpacaClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "acc123",
        "status": "ACTIVE",
        "buying_power": "50000.00",
        "cash": "50000.00",
        "equity": "50000.00",
    }
    mock_response.raise_for_status = MagicMock()

    client = AlpacaClient(api_key="test", secret_key="test", paper=True)
    with patch.object(client, "_request", new_callable=AsyncMock, return_value=mock_response.json.return_value):
        result = await client.get_account()

    assert result["id"] == "acc123"
    assert result["buying_power"] == "50000.00"


async def test_get_quote():
    from adapters.alpaca.client import AlpacaClient

    client = AlpacaClient(api_key="test", secret_key="test", paper=True)
    mock_data = {
        "symbol": "AAPL",
        "ap": 150.50,
        "bp": 150.45,
        "as": 100,
        "bs": 200,
        "t": "2026-03-30T12:00:00Z",
    }
    with patch.object(client, "_data_request", new_callable=AsyncMock, return_value=mock_data):
        result = await client.get_quote("AAPL")

    assert result["symbol"] == "AAPL"
    assert result["ap"] == 150.50


async def test_submit_order():
    from adapters.alpaca.client import AlpacaClient

    client = AlpacaClient(api_key="test", secret_key="test", paper=True)
    mock_response = {
        "id": "order123",
        "status": "filled",
        "filled_qty": "10",
        "filled_avg_price": "150.25",
        "symbol": "AAPL",
    }
    with patch.object(client, "_request", new_callable=AsyncMock, return_value=mock_response):
        result = await client.submit_order(
            symbol="AAPL", qty=10.0, side="buy", order_type="market", time_in_force="day",
        )

    assert result["id"] == "order123"
    assert result["status"] == "filled"


async def test_get_clock():
    from adapters.alpaca.client import AlpacaClient

    client = AlpacaClient(api_key="test", secret_key="test", paper=True)
    mock_response = {"is_open": True, "timestamp": "2026-03-30T12:00:00Z"}
    with patch.object(client, "_request", new_callable=AsyncMock, return_value=mock_response):
        result = await client.get_clock()

    assert result["is_open"] is True


async def test_base_urls():
    from adapters.alpaca.client import AlpacaClient

    paper = AlpacaClient(api_key="k", secret_key="s", paper=True)
    assert "paper" in paper._trading_base_url

    live = AlpacaClient(api_key="k", secret_key="s", paper=False)
    assert "paper" not in live._trading_base_url
