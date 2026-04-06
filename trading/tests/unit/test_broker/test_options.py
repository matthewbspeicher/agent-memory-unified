from datetime import date
from decimal import Decimal

from broker.models import Symbol, AssetType, OptionRight, OrderSide
from broker.options import build_iron_condor, build_collar


def test_build_iron_condor():
    underlying = Symbol(ticker="SPY", asset_type=AssetType.STOCK)
    expiry = date(2026, 4, 15)

    order = build_iron_condor(
        account_id="PAPER",
        underlying=underlying,
        quantity=Decimal("1"),
        expiry=expiry,
        short_put_strike=Decimal("490"),
        long_put_strike=Decimal("480"),
        short_call_strike=Decimal("510"),
        long_call_strike=Decimal("520"),
    )

    assert order.symbol == underlying
    assert order.account_id == "PAPER"
    assert order.quantity == Decimal("1")
    assert len(order.legs) == 4

    # Verify legs
    long_put = [
        l
        for l in order.legs
        if l.side == OrderSide.BUY and l.symbol.right == OptionRight.PUT
    ][0]
    assert long_put.symbol.strike == Decimal("480")

    short_put = [
        l
        for l in order.legs
        if l.side == OrderSide.SELL and l.symbol.right == OptionRight.PUT
    ][0]
    assert short_put.symbol.strike == Decimal("490")

    short_call = [
        l
        for l in order.legs
        if l.side == OrderSide.SELL and l.symbol.right == OptionRight.CALL
    ][0]
    assert short_call.symbol.strike == Decimal("510")

    long_call = [
        l
        for l in order.legs
        if l.side == OrderSide.BUY and l.symbol.right == OptionRight.CALL
    ][0]
    assert long_call.symbol.strike == Decimal("520")


def test_build_collar():
    underlying = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)
    expiry = date(2026, 4, 15)

    order = build_collar(
        account_id="PAPER",
        underlying=underlying,
        quantity=Decimal("100"),
        expiry=expiry,
        put_strike=Decimal("160"),
        call_strike=Decimal("180"),
    )

    assert len(order.legs) == 2

    buy_put = [l for l in order.legs if l.symbol.right == OptionRight.PUT][0]
    assert buy_put.side == OrderSide.BUY
    assert buy_put.symbol.strike == Decimal("160")

    sell_call = [l for l in order.legs if l.symbol.right == OptionRight.CALL][0]
    assert sell_call.side == OrderSide.SELL
    assert sell_call.symbol.strike == Decimal("180")
