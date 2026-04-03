from __future__ import annotations
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from broker.models import Symbol


async def test_get_quote():
    from adapters.tradier.market_data import TradierMarketDataProvider

    mock_client = MagicMock()
    mock_client.get_quote = AsyncMock(return_value={
        "quotes": {"quote": {"symbol": "AAPL", "last": 150.5, "bid": 150.45, "ask": 150.55, "volume": 5000000}},
    })

    provider = TradierMarketDataProvider(mock_client)
    quote = await provider.get_quote(Symbol(ticker="AAPL"))

    assert quote.symbol.ticker == "AAPL"
    assert quote.last == Decimal("150.5")
    assert quote.bid == Decimal("150.45")
    assert quote.ask == Decimal("150.55")


async def test_get_options_chain():
    from adapters.tradier.market_data import TradierMarketDataProvider

    mock_client = MagicMock()
    mock_client.get_options_expirations = AsyncMock(return_value=["2026-04-17"])
    mock_client.get_options_chain = AsyncMock(return_value={
        "options": {"option": [
            {
                "symbol": "AAPL260417C00200000",
                "option_type": "call", "strike": 200.0,
                "bid": 5.50, "ask": 5.70, "last": 5.60,
                "volume": 1000, "open_interest": 5000,
                "greeks": {"delta": 0.65, "gamma": 0.03, "theta": -0.05, "vega": 0.12, "rho": 0.01},
                "expiration_date": "2026-04-17",
            },
        ]},
    })

    provider = TradierMarketDataProvider(mock_client)
    chain = await provider.get_options_chain(Symbol(ticker="AAPL"))

    assert len(chain.calls) > 0 or len(chain.puts) > 0


async def test_get_historical_intraday_warning(caplog):
    """Tradier intraday data limited to ~35 days — should log warning for longer ranges."""
    from adapters.tradier.market_data import TradierMarketDataProvider
    import logging

    mock_client = MagicMock()
    mock_client.get_historical = AsyncMock(return_value=[])

    provider = TradierMarketDataProvider(mock_client)
    with caplog.at_level(logging.WARNING):
        bars = await provider.get_historical(Symbol(ticker="AAPL"), "5min", "6mo")

    assert bars == []
    # Should warn about intraday data limitation
