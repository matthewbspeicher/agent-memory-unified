from datetime import date
from decimal import Decimal
import pytest

from broker.models import Symbol, AssetType, OptionRight
from adapters.ibkr.symbols import to_contract, from_contract


class TestToContract:
    def test_stock(self):
        s = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)
        c = to_contract(s)
        assert c.symbol == "AAPL"
        assert c.secType == "STK"
        assert c.exchange == "SMART"
        assert c.currency == "USD"

    def test_stock_custom_exchange(self):
        s = Symbol(ticker="AAPL", asset_type=AssetType.STOCK, exchange="NYSE")
        c = to_contract(s)
        assert c.exchange == "NYSE"

    def test_option(self):
        s = Symbol(
            ticker="AAPL", asset_type=AssetType.OPTION,
            expiry=date(2026, 4, 17), strike=Decimal("200"),
            right=OptionRight.CALL, multiplier=100,
        )
        c = to_contract(s)
        assert c.symbol == "AAPL"
        assert c.secType == "OPT"
        assert c.lastTradeDateOrContractMonth == "20260417"
        assert c.strike == 200.0
        assert c.right == "C"

    def test_forex(self):
        s = Symbol(ticker="EUR.USD", asset_type=AssetType.FOREX)
        c = to_contract(s)
        assert c.symbol == "EUR"
        assert c.secType == "CASH"
        assert c.currency == "USD"
        assert c.exchange == "IDEALPRO"

    def test_future(self):
        s = Symbol(ticker="ES", asset_type=AssetType.FUTURE, expiry=date(2026, 12, 1), exchange="CME")
        c = to_contract(s)
        assert c.symbol == "ES"
        assert c.secType == "FUT"
        assert c.lastTradeDateOrContractMonth == "202612"
        assert c.exchange == "CME"


class TestFromContract:
    def test_stock_round_trip(self):
        s = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)
        c = to_contract(s)
        result = from_contract(c)
        assert result.ticker == "AAPL"
        assert result.asset_type == AssetType.STOCK
