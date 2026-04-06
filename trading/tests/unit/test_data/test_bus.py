# tests/unit/test_data/test_bus.py
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest

from broker.models import Bar, AccountBalance, Quote, Symbol
from data.bus import DataBus
from data.sources.base import DataSource


def _mock_source(name="mock", quotes=True, historical=True, options=False):
    source = MagicMock(spec=DataSource)
    source.name = name
    source.supports_quotes = quotes
    source.supports_historical = historical
    source.supports_options = options
    source.get_quote = AsyncMock()
    source.get_historical = AsyncMock()
    source.get_options_chain = AsyncMock()
    return source


def _make_quote(ticker="AAPL"):
    return Quote(
        symbol=Symbol(ticker=ticker),
        last=Decimal("150.00"),
        bid=Decimal("149.99"),
        ask=Decimal("150.01"),
        volume=1000000,
    )


def _make_bars(ticker="AAPL", count=20):
    sym = Symbol(ticker=ticker)
    return [
        Bar(
            symbol=sym,
            open=Decimal(str(100 + i)),
            high=Decimal(str(101 + i)),
            low=Decimal(str(99 + i)),
            close=Decimal(str(100 + i)),
            volume=1000,
            timestamp=datetime(2026, 1, i + 1),
        )
        for i in range(count)
    ]


class TestDataBusQuotes:
    async def test_get_quote_from_supplemental(self):
        source = _mock_source()
        source.get_quote.return_value = _make_quote()
        bus = DataBus(sources=[source])
        result = await bus.get_quote(Symbol(ticker="AAPL"))
        assert result.last == Decimal("150.00")
        source.get_quote.assert_awaited_once()

    async def test_get_quote_cached(self):
        source = _mock_source()
        source.get_quote.return_value = _make_quote()
        bus = DataBus(sources=[source])
        await bus.get_quote(Symbol(ticker="AAPL"))
        await bus.get_quote(Symbol(ticker="AAPL"))
        assert source.get_quote.await_count == 1  # cached

    async def test_get_quotes_multiple(self):
        source = _mock_source()
        source.get_quote.return_value = _make_quote()
        bus = DataBus(sources=[source])
        syms = [Symbol(ticker="AAPL"), Symbol(ticker="MSFT")]
        results = await bus.get_quotes(syms)
        assert len(results) == 2


class TestDataBusHistorical:
    async def test_get_historical(self):
        source = _mock_source()
        source.get_historical.return_value = _make_bars()
        bus = DataBus(sources=[source])
        bars = await bus.get_historical(Symbol(ticker="AAPL"), "1d", "3mo")
        assert len(bars) == 20

    async def test_get_historical_cached(self):
        source = _mock_source()
        source.get_historical.return_value = _make_bars()
        bus = DataBus(sources=[source])
        sym = Symbol(ticker="AAPL")
        await bus.get_historical(sym, "1d", "3mo")
        await bus.get_historical(sym, "1d", "3mo")
        assert source.get_historical.await_count == 1


class TestDataBusIndicators:
    async def test_get_rsi(self):
        source = _mock_source()
        source.get_historical.return_value = _make_bars(count=30)
        bus = DataBus(sources=[source])
        rsi = await bus.get_rsi(Symbol(ticker="AAPL"), 14)
        assert 0 <= rsi <= 100

    async def test_get_sma(self):
        source = _mock_source()
        source.get_historical.return_value = _make_bars(count=25)
        bus = DataBus(sources=[source])
        sma = await bus.get_sma(Symbol(ticker="AAPL"), 20)
        assert isinstance(sma, float)

    async def test_get_bollinger_accepts_num_std(self):
        source = _mock_source()
        source.get_historical.return_value = _make_bars(count=30)
        bus = DataBus(sources=[source])
        bands = await bus.get_bollinger(Symbol(ticker="AAPL"), period=20, num_std=2.5)
        assert bands.upper > bands.middle > bands.lower


class TestDataBusPortfolio:
    async def test_get_positions(self):
        source = _mock_source()
        broker = MagicMock()
        broker.account.get_positions = AsyncMock(return_value=[])
        bus = DataBus(sources=[source], broker=broker)
        positions = await bus.get_positions()
        assert positions == []
        broker.account.get_positions.assert_awaited_once()

    async def test_get_balances(self):
        broker = MagicMock()
        balance = AccountBalance(
            account_id="U123",
            net_liquidation=Decimal("100000"),
            buying_power=Decimal("50000"),
            cash=Decimal("30000"),
            maintenance_margin=Decimal("20000"),
        )
        broker.account.get_balances = AsyncMock(return_value=balance)
        bus = DataBus(sources=[], broker=broker)
        result = await bus.get_balances()
        assert result.net_liquidation == Decimal("100000")


class TestDataBusFallbacks:
    async def test_skips_recursive_broker_fallback_when_market_data_uses_bus(self):
        failing_source = _mock_source(name="failing")
        failing_source.get_quote.side_effect = RuntimeError("primary source down")

        broker = MagicMock()
        broker_market_data = MagicMock()
        broker_market_data._data_bus = None
        broker.market_data = broker_market_data

        bus = DataBus(sources=[failing_source], broker=broker)
        broker_market_data._data_bus = bus

        with pytest.raises(RuntimeError, match="No source available for get_quote"):
            await bus.get_quote(Symbol(ticker="AAPL"))
