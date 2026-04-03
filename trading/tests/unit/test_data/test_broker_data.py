import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime

from broker.models import Symbol, AssetType, Bar
from data.sources.broker_data import BrokerHistoricalSource

@pytest.fixture
def source():
    return BrokerHistoricalSource()

@pytest.mark.asyncio
async def test_format_ticker(source):
    # Test multi-class stocks
    assert source._format_ticker(Symbol("BRK B")) == "BRK-B"
    
    # Test indices
    assert source._format_ticker(Symbol("SPX", asset_type=AssetType.STOCK)) == "^SPX"
    assert source._format_ticker(Symbol("NDX", asset_type=AssetType.STOCK)) == "^NDX"
    
    # Test normal stocks
    assert source._format_ticker(Symbol("AAPL")) == "AAPL"

@pytest.mark.asyncio
async def test_get_historical_success(source):
    # Mock data
    data = {
        "Open": [100.0, 101.0],
        "High": [105.0, 106.0],
        "Low": [99.0, 98.0],
        "Close": [102.0, 103.0],
        "Volume": [1000, 1100]
    }
    df = pd.DataFrame(data, index=[pd.Timestamp("2026-03-26"), pd.Timestamp("2026-03-27")])
    
    with patch("yfinance.download", return_value=df):
        symbol = Symbol("AAPL")
        bars = await source.get_historical(symbol)
        
        assert len(bars) == 2
        assert bars[0].symbol == symbol
        assert bars[0].open == Decimal("100.0")
        assert bars[0].close == Decimal("102.0")
        assert bars[0].volume == 1000
        assert isinstance(bars[0].timestamp, datetime)

@pytest.mark.asyncio
async def test_get_historical_empty(source):
    with patch("yfinance.download", return_value=pd.DataFrame()):
        symbol = Symbol("INVALID")
        bars = await source.get_historical(symbol)
        assert len(bars) == 0

@pytest.mark.asyncio
async def test_get_historical_multi_index(source):
    # Mock multi-index dataframe (sometimes returned by yfinance)
    columns = pd.MultiIndex.from_tuples([("Open", "AAPL"), ("Close", "AAPL"), ("High", "AAPL"), ("Low", "AAPL"), ("Volume", "AAPL")], names=[None, "Ticker"])
    data = [[100.0, 102.0, 105.0, 99.0, 1000]]
    df = pd.DataFrame(data, columns=columns, index=[pd.Timestamp("2026-03-27")])
    
    with patch("yfinance.download", return_value=df):
        symbol = Symbol("AAPL")
        bars = await source.get_historical(symbol)
        assert len(bars) == 1
        assert bars[0].close == Decimal("102.0")
