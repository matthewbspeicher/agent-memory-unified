from __future__ import annotations
from unittest.mock import AsyncMock, patch


async def test_get_profile():
    from adapters.tradier.client import TradierClient

    client = TradierClient(token="test", account_id="acc1", sandbox=True)
    mock_data = {"profile": {"account": {"account_number": "acc1", "status": "active"}}}
    with patch.object(
        client, "_request", new_callable=AsyncMock, return_value=mock_data
    ):
        result = await client.get_profile()

    assert result["profile"]["account"]["account_number"] == "acc1"


async def test_get_quote():
    from adapters.tradier.client import TradierClient

    client = TradierClient(token="test", account_id="acc1", sandbox=True)
    mock_data = {
        "quotes": {
            "quote": {"symbol": "AAPL", "last": 150.5, "bid": 150.45, "ask": 150.55}
        }
    }
    with patch.object(
        client, "_request", new_callable=AsyncMock, return_value=mock_data
    ):
        result = await client.get_quote("AAPL")

    assert result["quotes"]["quote"]["symbol"] == "AAPL"


async def test_get_options_chain():
    from adapters.tradier.client import TradierClient

    client = TradierClient(token="test", account_id="acc1", sandbox=True)
    mock_data = {
        "options": {
            "option": [
                {
                    "symbol": "AAPL210917C00145000",
                    "option_type": "call",
                    "strike": 145.0,
                    "bid": 5.50,
                    "ask": 5.70,
                    "last": 5.60,
                    "volume": 1000,
                    "open_interest": 5000,
                    "greeks": {
                        "delta": 0.65,
                        "gamma": 0.03,
                        "theta": -0.05,
                        "vega": 0.12,
                        "rho": 0.01,
                    },
                },
            ]
        },
    }
    with patch.object(
        client, "_request", new_callable=AsyncMock, return_value=mock_data
    ):
        result = await client.get_options_chain("AAPL", "2021-09-17")

    chain = result["options"]["option"]
    assert len(chain) == 1
    assert chain[0]["greeks"]["delta"] == 0.65


async def test_base_urls():
    from adapters.tradier.client import TradierClient

    sandbox = TradierClient(token="t", account_id="a", sandbox=True)
    assert "sandbox" in sandbox._base_url

    live = TradierClient(token="t", account_id="a", sandbox=False)
    assert "sandbox" not in live._base_url


async def test_place_order():
    from adapters.tradier.client import TradierClient

    client = TradierClient(token="test", account_id="acc1", sandbox=True)
    mock_data = {"order": {"id": 12345, "status": "ok"}}
    with patch.object(
        client, "_request", new_callable=AsyncMock, return_value=mock_data
    ):
        result = await client.place_order(
            symbol="AAPL",
            side="buy",
            qty=10,
            order_type="market",
            duration="day",
        )

    assert result["order"]["id"] == 12345
