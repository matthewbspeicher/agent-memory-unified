from decimal import Decimal as D
import pytest
from broker.models import (
    AccountBalance,
    Symbol,
    Position,
    MarketOrder,
    OrderSide,
    Quote,
)
from risk.rules import PortfolioContext, MaxPortfolioExposure


def context(held=0, *, equity="1000"):
    sym = Symbol("TEST")
    return PortfolioContext(
        positions=[Position(sym, D(held), D(100), D(held) * 100, D(0), D(0))]
        if held
        else [],
        balance=AccountBalance("paper", D(equity), D(equity), D(equity), D(0)),
    )


def check(ctx, qty, side=OrderSide.BUY, cap=60):
    trade = MarketOrder(Symbol("TEST"), side, D(qty), "paper")
    return MaxPortfolioExposure(cap).evaluate(
        trade, Quote(trade.symbol, last=D(100)), ctx
    )


@pytest.mark.parametrize(
    "held,qty,side,passed",
    [
        (4, 2, OrderSide.BUY, True),
        (4, 3, OrderSide.BUY, False),
        (-4, 2, OrderSide.SELL, True),
        (-4, 3, OrderSide.SELL, False),
        (4, 4, OrderSide.SELL, True),
        (-4, 4, OrderSide.BUY, True),
        (4, 11, OrderSide.SELL, False),
    ],
)
def test_gross_holdings_and_crossing_zero(held, qty, side, passed):
    assert check(context(held), qty, side).passed == passed


def test_opposite_pending_orders_never_net_away_capacity():
    ctx = context()
    sym = Symbol("TEST")
    ctx.pending_exposure = [
        (MarketOrder(sym, OrderSide.BUY, D(6), "paper"), D(6)),
        (MarketOrder(sym, OrderSide.SELL, D(6), "paper"), D(6)),
    ]
    ctx.exposure_prices = {sym: D(100)}
    assert not check(ctx, 1).passed


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0"])
def test_bad_equity_fails_closed(value):
    assert not check(context(equity=value), 1).passed


@pytest.mark.parametrize(
    "field,value",
    [("market_value", "NaN"), ("market_value", "0"), ("quantity", "Infinity")],
)
def test_unvalued_holdings_fail_closed(field, value):
    from dataclasses import replace

    ctx = context(4)
    ctx.positions[0] = replace(ctx.positions[0], **{field: D(value)})
    assert not check(ctx, 1).passed


def test_external_gross_positions_count_without_netting():
    ctx = context()
    ctx.external_positions = [{"symbol": "OTHER", "quantity": -6, "market_value": -600}]
    assert not check(ctx, 1).passed
    ctx.external_positions[0].pop("market_value")
    assert not check(ctx, 1).passed
