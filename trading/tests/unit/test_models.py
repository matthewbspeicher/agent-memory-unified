from decimal import Decimal
from datetime import date, datetime
import pytest

from broker.models import (
    Symbol, AssetType, OptionRight, OrderSide, TIF,
    MarketOrder, LimitOrder, StopOrder, StopLimitOrder, TrailingStopOrder,
    Quote, Bar, Position, AccountBalance, OrderResult, OrderStatus,
)


class TestSymbol:
    def test_stock_symbol(self):
        s = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)
        assert s.ticker == "AAPL"
        assert s.asset_type == AssetType.STOCK
        assert s.currency == "USD"
        assert s.expiry is None

    def test_option_symbol(self):
        s = Symbol(
            ticker="AAPL",
            asset_type=AssetType.OPTION,
            expiry=date(2026, 4, 17),
            strike=Decimal("200"),
            right=OptionRight.CALL,
            multiplier=100,
        )
        assert s.strike == Decimal("200")
        assert s.right == OptionRight.CALL

    def test_forex_symbol(self):
        s = Symbol(ticker="EUR.USD", asset_type=AssetType.FOREX, exchange="IDEALPRO")
        assert s.exchange == "IDEALPRO"

    def test_future_symbol(self):
        s = Symbol(ticker="ESZ6", asset_type=AssetType.FUTURE, exchange="CME")
        assert s.asset_type == AssetType.FUTURE


class TestOrders:
    def test_market_order(self):
        s = Symbol(ticker="AAPL")
        o = MarketOrder(symbol=s, side=OrderSide.BUY, quantity=Decimal("100"), account_id="U12345")
        assert o.time_in_force == TIF.DAY

    def test_limit_order(self):
        s = Symbol(ticker="AAPL")
        o = LimitOrder(
            symbol=s, side=OrderSide.BUY, quantity=Decimal("100"),
            account_id="U12345", limit_price=Decimal("150.00"),
        )
        assert o.limit_price == Decimal("150.00")

    def test_trailing_stop_with_amount(self):
        s = Symbol(ticker="AAPL")
        o = TrailingStopOrder(
            symbol=s, side=OrderSide.SELL, quantity=Decimal("50"),
            account_id="U12345", trail_amount=Decimal("5.00"),
        )
        assert o.trail_amount == Decimal("5.00")
        assert o.trail_percent is None

    def test_trailing_stop_both_raises(self):
        s = Symbol(ticker="AAPL")
        with pytest.raises(ValueError, match="exactly one"):
            TrailingStopOrder(
                symbol=s, side=OrderSide.SELL, quantity=Decimal("50"),
                account_id="U12345", trail_amount=Decimal("5"), trail_percent=Decimal("1"),
            )

    def test_trailing_stop_neither_raises(self):
        s = Symbol(ticker="AAPL")
        with pytest.raises(ValueError, match="exactly one"):
            TrailingStopOrder(
                symbol=s, side=OrderSide.SELL, quantity=Decimal("50"),
                account_id="U12345",
            )


class TestOrderResult:
    def test_order_result_has_commission_and_filled_at(self):
        filled_time = datetime(2026, 3, 25, 10, 30, 0)
        result = OrderResult(
            order_id="12345",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("100"),
            avg_fill_price=Decimal("150.50"),
            commission=Decimal("10.50"),
            filled_at=filled_time,
        )
        assert result.commission == Decimal("10.50")
        assert result.filled_at == filled_time

    def test_order_result_commission_defaults_to_zero(self):
        result = OrderResult(
            order_id="12345",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("100"),
        )
        assert result.commission == Decimal("0")
        assert result.filled_at is None
