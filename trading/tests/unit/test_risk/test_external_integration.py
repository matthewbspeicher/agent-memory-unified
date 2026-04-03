from decimal import Decimal

from broker.models import (
    AccountBalance, MarketOrder, OrderSide, Position, Quote, Symbol,
)
from risk.rules import MaxPortfolioExposure, MaxPositionSize, PortfolioContext


def _balance(net_liq: float) -> AccountBalance:
    return AccountBalance(
        account_id="U123",
        net_liquidation=Decimal(str(net_liq)),
        buying_power=Decimal("0"),
        cash=Decimal("0"),
        maintenance_margin=Decimal("0"),
    )


def _position(ticker: str, qty: float) -> Position:
    return Position(
        symbol=Symbol(ticker=ticker),
        quantity=Decimal(str(qty)),
        avg_cost=Decimal("0"),
        market_value=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
    )


def test_max_position_size_includes_external():
    # IBKR has 50 shares AAPL, external has 100 shares AAPL, trade wants 1 more
    # total would be 151 > max_shares=120 → should FAIL
    ctx = PortfolioContext(
        positions=[_position("AAPL", 50)],
        balance=_balance(100000),
        external_positions=[{"symbol": "AAPL", "quantity": 100}],
    )
    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        account_id="U123",
    )
    quote = Quote(symbol=Symbol(ticker="AAPL"), last=Decimal("150"))
    rule = MaxPositionSize(max_dollars=1_000_000, max_shares=120)
    result = rule.evaluate(trade, quote, ctx)
    assert not result.passed
    assert "120" in result.reason


def test_max_portfolio_exposure_includes_external():
    # IBKR net_liq=50000, external net_liq=50000 → total=100000
    # trade value = 100 * $150 = $15000 → 15% of 100k → passes 20% limit
    ctx = PortfolioContext(
        positions=[],
        balance=_balance(50000),
        external_balances=[{"net_liquidation": 50000}],
    )
    trade = MarketOrder(
        symbol=Symbol(ticker="MSFT"),
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        account_id="U123",
    )
    quote = Quote(symbol=Symbol(ticker="MSFT"), last=Decimal("150"))
    rule = MaxPortfolioExposure(max_percent=20.0)
    result = rule.evaluate(trade, quote, ctx)
    assert result.passed
