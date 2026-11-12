"""Rule-level regressions for shared execution admission."""

from decimal import Decimal

import pytest

from broker.models import (
    AccountBalance,
    AssetType,
    MarketOrder,
    OrderSide,
    Position,
    Quote,
    Symbol,
)
from risk.rules import (
    MaxDailyLoss,
    MaxDailyTrades,
    MaxOpenPositions,
    MaxPositionSize,
    MaxPredictionExposure,
    PortfolioContext,
)


def context(*positions, **metrics):
    return PortfolioContext(
        positions=list(positions),
        balance=AccountBalance(
            "paper", Decimal("10000"), Decimal("10000"), Decimal("10000"), Decimal("0")
        ),
        **metrics,
    )


def position(quantity, symbol=Symbol("TEST")):
    return Position(
        symbol,
        Decimal(str(quantity)),
        Decimal("10"),
        Decimal(str(quantity)) * 10,
        Decimal("0"),
        Decimal("0"),
    )


def trade(quantity, side=OrderSide.BUY, symbol=Symbol("TEST")):
    return MarketOrder(symbol, side, Decimal(str(quantity)), "paper")


def quote(symbol=Symbol("TEST"), price="10"):
    return Quote(symbol, last=Decimal(price))


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
def test_position_share_cap_applies_to_long_and_short(side):
    result = MaxPositionSize(10000, 10).evaluate(trade(11, side), quote(), context())
    assert not result.passed
    assert "max shares" in result.reason


@pytest.mark.parametrize("existing,side", [(9, OrderSide.BUY), (-9, OrderSide.SELL)])
def test_split_orders_cannot_exceed_projected_position_dollar_cap(existing, side):
    result = MaxPositionSize(100, 100).evaluate(
        trade(2, side), quote(), context(position(existing))
    )
    assert not result.passed
    assert "Projected position value" in result.reason


def test_projection_sums_duplicate_holdings_for_same_symbol():
    result = MaxPositionSize(10000, 10).evaluate(
        trade(1), quote(), context(position(5), position(5))
    )
    assert not result.passed


def test_same_ticker_with_different_asset_type_is_not_netted():
    stock = Symbol("TEST", AssetType.STOCK)
    prediction = Symbol("TEST", AssetType.PREDICTION)
    result = MaxPositionSize(10000, 10).evaluate(
        trade(11, symbol=stock), quote(stock), context(position(-10, prediction))
    )
    assert not result.passed


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
def test_prediction_cap_applies_to_absolute_exposure(side):
    symbol = Symbol("WIN", AssetType.PREDICTION)
    result = MaxPredictionExposure(50).evaluate(
        trade(101, side, symbol), quote(symbol, "0.5"), context()
    )
    assert not result.passed


def test_crossing_zero_still_checks_new_short_exposure():
    result = MaxPositionSize(10000, 10).evaluate(
        trade(21, OrderSide.SELL), quote(), context(position(10))
    )
    assert not result.passed


@pytest.mark.parametrize(
    "side,quantity", [(OrderSide.SELL, 5), (OrderSide.SELL, 10), (OrderSide.BUY, 1)]
)
def test_position_count_cap_allows_existing_symbol(side, quantity):
    result = MaxOpenPositions(1).evaluate(
        trade(quantity, side), quote(), context(position(10))
    )
    assert result.passed


def test_position_count_blocks_new_symbol_at_cap():
    result = MaxOpenPositions(1).evaluate(
        trade(1), quote(), context(position(10, Symbol("OTHER")))
    )
    assert not result.passed


def test_closed_rows_do_not_consume_open_position_capacity():
    result = MaxOpenPositions(1).evaluate(
        trade(1), quote(), context(position(0, Symbol("OTHER")))
    )
    assert result.passed


def test_duplicate_symbol_rows_count_as_one_open_position():
    result = MaxOpenPositions(2).evaluate(
        trade(1),
        quote(),
        context(position(2, Symbol("OTHER")), position(3, Symbol("OTHER"))),
    )
    assert result.passed


@pytest.mark.parametrize("value", [None, Decimal("NaN"), Decimal("Infinity"), 0])
def test_daily_loss_rejects_unavailable_or_invalid_metric(value):
    result = MaxDailyLoss(100).evaluate(trade(1), quote(), context(daily_pnl=value))
    assert not result.passed
    assert "unavailable or invalid" in result.reason


@pytest.mark.parametrize("value", [None, -1, True, 0.0])
def test_daily_trade_limit_rejects_unavailable_or_invalid_metric(value):
    result = MaxDailyTrades(10).evaluate(
        trade(1), quote(), context(daily_trade_count=value)
    )
    assert not result.passed
    assert "unavailable or invalid" in result.reason


def test_measured_zero_is_distinct_from_unknown_daily_metrics():
    unknown = context()
    assert unknown.daily_pnl is None
    assert unknown.daily_trade_count is None
    measured = context(daily_pnl=Decimal("0"), daily_trade_count=0)
    assert MaxDailyLoss(100).evaluate(trade(1), quote(), measured).passed
    assert MaxDailyTrades(10).evaluate(trade(1), quote(), measured).passed


@pytest.mark.asyncio
async def test_later_sizing_cannot_invalidate_earlier_projected_position_check():
    from risk.engine import RiskEngine
    from risk.kill_switch import KillSwitch
    from risk.rules import RiskRule, RiskResult

    class ReduceSize(RiskRule):
        name = "reduce_size"

        def evaluate(self, order, quote, ctx):
            return RiskResult(passed=True, adjusted_quantity=Decimal("1"))

    engine = RiskEngine([MaxPositionSize(10000, 10), ReduceSize()], KillSwitch())
    result = await engine.evaluate_order(
        trade(10, OrderSide.SELL), quote(), context(position(20))
    )
    assert not result.passed
    assert result.rule_name == "max_position_size"
