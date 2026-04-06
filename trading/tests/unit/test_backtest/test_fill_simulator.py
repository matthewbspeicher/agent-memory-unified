from decimal import Decimal
from data.backtest import FillSimulator
from broker.models import LimitOrder, MarketOrder, Symbol, AssetType, OrderSide


def _symbol(ticker: str = "AAPL") -> Symbol:
    return Symbol(ticker=ticker, asset_type=AssetType.STOCK)


class TestFillSimulator:
    def test_market_order_fills_at_close_with_slippage(self):
        sim = FillSimulator(
            slippage_pct=Decimal("0.001"), fee_per_trade=Decimal("1.00")
        )
        order = MarketOrder(
            symbol=_symbol(),
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id="TEST",
        )
        fill = sim.simulate(order, bar_close=Decimal("150.00"))
        assert fill is not None
        assert fill.price == Decimal("150.15")  # 150 * 1.001
        assert fill.fees == Decimal("1.00")

    def test_sell_slippage_goes_down(self):
        sim = FillSimulator(slippage_pct=Decimal("0.001"), fee_per_trade=Decimal("0"))
        order = MarketOrder(
            symbol=_symbol(),
            side=OrderSide.SELL,
            quantity=Decimal("10"),
            account_id="TEST",
        )
        fill = sim.simulate(order, bar_close=Decimal("150.00"))
        assert fill.price == Decimal("149.85")  # 150 * 0.999

    def test_limit_buy_fills_when_low_reaches_limit(self):
        sim = FillSimulator(slippage_pct=Decimal("0"), fee_per_trade=Decimal("0"))
        order = LimitOrder(
            symbol=_symbol(),
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id="TEST",
            limit_price=Decimal("148.00"),
        )
        fill = sim.simulate(order, bar_close=Decimal("150"), bar_low=Decimal("147"))
        assert fill is not None
        assert fill.price == Decimal("148.00")

    def test_limit_buy_no_fill_above_limit(self):
        sim = FillSimulator(slippage_pct=Decimal("0"), fee_per_trade=Decimal("0"))
        order = LimitOrder(
            symbol=_symbol(),
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id="TEST",
            limit_price=Decimal("145.00"),
        )
        fill = sim.simulate(order, bar_close=Decimal("150"), bar_low=Decimal("148"))
        assert fill is None

    def test_zero_slippage(self):
        sim = FillSimulator(slippage_pct=Decimal("0"), fee_per_trade=Decimal("0"))
        order = MarketOrder(
            symbol=_symbol(),
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id="TEST",
        )
        fill = sim.simulate(order, bar_close=Decimal("100"))
        assert fill.price == Decimal("100")
