import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock

from broker.models import Symbol, Bar
from data.backtest import HistoricalDataSource, ReplayDataBus

@pytest.fixture
def sample_bars():
    symbol = Symbol("AAPL")
    return {
        "AAPL": [
            Bar(symbol=symbol, timestamp=datetime(2026, 3, 20, tzinfo=timezone.utc), close=Decimal("150.0")),
            Bar(symbol=symbol, timestamp=datetime(2026, 3, 21, tzinfo=timezone.utc), close=Decimal("152.0")),
            Bar(symbol=symbol, timestamp=datetime(2026, 3, 22, tzinfo=timezone.utc), close=Decimal("151.0")),
        ]
    }

@pytest.mark.asyncio
async def test_historical_data_source_replay(sample_bars):
    source = HistoricalDataSource(sample_bars)
    symbol = Symbol("AAPL")
    
    # Test without current_time
    with pytest.raises(ValueError, match="current_time not set"):
        await source.get_quote(symbol)
        
    # Set time to first bar
    source.current_time = datetime(2026, 3, 20, tzinfo=timezone.utc)
    quote = await source.get_quote(symbol)
    assert quote.last == Decimal("150.0")
    
    # Set time to between bars
    source.current_time = datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc)
    quote = await source.get_quote(symbol)
    assert quote.last == Decimal("152.0")
    
    # Test historical call
    bars = await source.get_historical(symbol)
    assert len(bars) == 2
    assert bars[-1].close == Decimal("152.0")

@pytest.mark.asyncio
async def test_replay_data_bus_integration(sample_bars):
    source = HistoricalDataSource(sample_bars)
    bus = ReplayDataBus(source, starting_balance=Decimal("10000.0"))
    
    # Advance time
    bus.advance_time(datetime(2026, 3, 21, tzinfo=timezone.utc))
    
    quote = await bus.get_quote(Symbol("AAPL"))
    assert quote.last == Decimal("152.0")
    
    balances = await bus.get_balances()
    assert balances.cash == Decimal("10000.0")
    assert balances.net_liquidation == Decimal("10000.0")

@pytest.mark.asyncio
async def test_load_replay_source():
    from data.backtest import load_replay_source
    from unittest.mock import patch
    
    symbol = Symbol("AAPL")
    mock_bars = [Bar(symbol=symbol, timestamp=datetime.now(), close=Decimal("150.0"))]
    
    with patch("data.sources.broker_data.BrokerHistoricalSource.get_historical", return_value=mock_bars):
        source = await load_replay_source([symbol])
        assert "AAPL" in source.bars
        assert len(source.bars["AAPL"]) == 1
