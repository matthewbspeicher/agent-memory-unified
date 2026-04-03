import pytest
from broker.models import AssetType
from data.universe import get_universe


class TestGetUniverse:
    def test_sp500_returns_symbols(self):
        symbols = get_universe("SP500")
        assert len(symbols) > 0
        tickers = [s.ticker for s in symbols]
        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_nasdaq100_returns_symbols(self):
        symbols = get_universe("NASDAQ100")
        assert len(symbols) > 0
        assert all(s.asset_type == AssetType.STOCK for s in symbols)

    def test_case_insensitive(self):
        upper = get_universe("SP500")
        lower = get_universe("sp500")
        assert len(upper) == len(lower)

    def test_explicit_list(self):
        symbols = get_universe(["AAPL", "TSLA", "GOOG"])
        assert len(symbols) == 3
        assert symbols[0].ticker == "AAPL"

    def test_unknown_universe_raises(self):
        with pytest.raises(ValueError, match="Unknown universe"):
            get_universe("NONEXISTENT")
