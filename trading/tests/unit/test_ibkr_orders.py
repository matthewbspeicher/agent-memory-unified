from decimal import Decimal

from broker.models import (
    Symbol,
    OrderSide,
    TIF,
    MarketOrder,
    LimitOrder,
    StopOrder,
    StopLimitOrder,
    TrailingStopOrder,
)
from adapters.ibkr.orders import to_ib_order


class TestToIBOrder:
    def setup_method(self):
        self.symbol = Symbol(ticker="AAPL")

    def test_market_order(self):
        order = MarketOrder(
            symbol=self.symbol,
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            account_id="U12345",
        )
        ib_order = to_ib_order(order)
        assert ib_order.orderType == "MKT"
        assert ib_order.action == "BUY"
        assert ib_order.totalQuantity == 100
        assert ib_order.tif == "DAY"

    def test_limit_order(self):
        order = LimitOrder(
            symbol=self.symbol,
            side=OrderSide.SELL,
            quantity=Decimal("50"),
            account_id="U12345",
            limit_price=Decimal("150.50"),
        )
        ib_order = to_ib_order(order)
        assert ib_order.orderType == "LMT"
        assert ib_order.lmtPrice == 150.50
        assert ib_order.action == "SELL"

    def test_stop_order(self):
        order = StopOrder(
            symbol=self.symbol,
            side=OrderSide.SELL,
            quantity=Decimal("25"),
            account_id="U12345",
            stop_price=Decimal("140.00"),
        )
        ib_order = to_ib_order(order)
        assert ib_order.orderType == "STP"
        assert ib_order.auxPrice == 140.0

    def test_stop_limit_order(self):
        order = StopLimitOrder(
            symbol=self.symbol,
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id="U12345",
            stop_price=Decimal("155.00"),
            limit_price=Decimal("156.00"),
        )
        ib_order = to_ib_order(order)
        assert ib_order.orderType == "STP LMT"
        assert ib_order.auxPrice == 155.0
        assert ib_order.lmtPrice == 156.0

    def test_trailing_stop_amount(self):
        order = TrailingStopOrder(
            symbol=self.symbol,
            side=OrderSide.SELL,
            quantity=Decimal("100"),
            account_id="U12345",
            trail_amount=Decimal("5.00"),
        )
        ib_order = to_ib_order(order)
        assert ib_order.orderType == "TRAIL"
        assert ib_order.auxPrice == 5.0

    def test_trailing_stop_percent(self):
        order = TrailingStopOrder(
            symbol=self.symbol,
            side=OrderSide.SELL,
            quantity=Decimal("100"),
            account_id="U12345",
            trail_percent=Decimal("2.5"),
        )
        ib_order = to_ib_order(order)
        assert ib_order.orderType == "TRAIL"
        assert ib_order.trailingPercent == 2.5

    def test_gtc_time_in_force(self):
        order = MarketOrder(
            symbol=self.symbol,
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            account_id="U12345",
            time_in_force=TIF.GTC,
        )
        ib_order = to_ib_order(order)
        assert ib_order.tif == "GTC"
