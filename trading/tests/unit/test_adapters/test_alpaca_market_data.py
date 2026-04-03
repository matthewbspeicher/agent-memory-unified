from __future__ import annotations
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from broker.models import Symbol


async def test_get_quote_maps_correctly():
    from adapters.alpaca.market_data import AlpacaMarketDataProvider

    mock_client = MagicMock()
    mock_client.get_quote = AsyncMock(return_value={
        "quote": {
            "ap": 150.50,
            "bp": 150.45,
            "as": 100,
            "bs": 200,
            "t": "2026-03-30T12:00:00Z",
        }
    })

    provider = AlpacaMarketDataProvider(mock_client)
    quote = await provider.get_quote(Symbol(ticker="AAPL"))

    assert quote.symbol.ticker == "AAPL"
    assert quote.ask == Decimal("150.50")
    assert quote.bid == Decimal("150.45")
    assert quote.last == Decimal("150.475")


async def test_get_historical_maps_bars():
    from adapters.alpaca.market_data import AlpacaMarketDataProvider

    mock_client = MagicMock()
    mock_client.get_bars = AsyncMock(return_value=[
        {"t": "2026-03-30T12:00:00Z", "o": 150.0, "h": 151.0, "l": 149.0, "c": 150.5, "v": 1000},
        {"t": "2026-03-30T12:01:00Z", "o": 150.5, "h": 152.0, "l": 150.0, "c": 151.5, "v": 1200},
    ])

    provider = AlpacaMarketDataProvider(mock_client)
    bars = await provider.get_historical(Symbol(ticker="AAPL"), "1d", "3mo")

    assert len(bars) == 2
    assert bars[0].open == Decimal("150.0")
    assert bars[1].close == Decimal("151.5")
    mock_client.get_bars.assert_awaited_once()
    assert mock_client.get_bars.await_args.args[1] == "1Day"


async def test_get_options_chain_not_implemented():
    from adapters.alpaca.market_data import AlpacaMarketDataProvider

    provider = AlpacaMarketDataProvider(MagicMock())
    with pytest.raises(NotImplementedError):
        await provider.get_options_chain(Symbol(ticker="AAPL"))
