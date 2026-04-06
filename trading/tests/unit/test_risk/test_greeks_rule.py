# tests/unit/test_risk/test_greeks_rule.py
from datetime import date
from decimal import Decimal

from broker.models import (
    Symbol,
    AssetType,
    OptionRight,
    OrderSide,
    Quote,
    AccountBalance,
    OptionLeg,
    ComboOrder,
    MarketOrder,
)
from risk.greeks import estimate_option_delta
from risk.rules import MaxComboDelta, PortfolioContext


def test_estimate_option_delta():
    # Call ATM
    delta = estimate_option_delta(
        Decimal("100"), Decimal("100"), OptionRight.CALL, date.today()
    )
    assert delta == Decimal("0.50")

    # Put ATM
    delta = estimate_option_delta(
        Decimal("100"), Decimal("100"), OptionRight.PUT, date.today()
    )
    assert delta == Decimal("-0.50")

    # Call deeply ITM (S=120, K=100 -> ratio 1.2 > 1.1)
    delta = estimate_option_delta(
        Decimal("120"), Decimal("100"), OptionRight.CALL, date.today()
    )
    assert delta == Decimal("1.00")

    # Put deeply ITM (S=80, K=100 -> ratio 0.8 < 0.9)
    delta = estimate_option_delta(
        Decimal("80"), Decimal("100"), OptionRight.PUT, date.today()
    )
    assert delta == Decimal("-1.00")

    # Call OTM (S=90, K=100 -> ratio 0.9) -> Delta 0
    delta = estimate_option_delta(
        Decimal("90"), Decimal("100"), OptionRight.CALL, date.today()
    )
    assert delta == Decimal("0.00")


def test_max_combo_delta_rule_pass():
    rule = MaxComboDelta(max_abs_delta=100)  # Max 100 delta

    # Create Iron Condor (Delta neutral-ish)
    # Underlying at 100
    # Long Put 90 (delta 0), Short Put 95 (delta ~-0.25)
    # Short Call 105 (delta ~0.25), Long Call 110 (delta 0)
    # Net delta should be close to 0
    legs = [
        OptionLeg(
            symbol=Symbol(
                "AAPL",
                AssetType.OPTION,
                right=OptionRight.PUT,
                strike=Decimal("90"),
                expiry=date.today(),
                multiplier=100,
            ),
            side=OrderSide.BUY,
            ratio=1,
        ),
        OptionLeg(
            symbol=Symbol(
                "AAPL",
                AssetType.OPTION,
                right=OptionRight.PUT,
                strike=Decimal("95"),
                expiry=date.today(),
                multiplier=100,
            ),
            side=OrderSide.SELL,
            ratio=1,
        ),
        OptionLeg(
            symbol=Symbol(
                "AAPL",
                AssetType.OPTION,
                right=OptionRight.CALL,
                strike=Decimal("105"),
                expiry=date.today(),
                multiplier=100,
            ),
            side=OrderSide.SELL,
            ratio=1,
        ),
        OptionLeg(
            symbol=Symbol(
                "AAPL",
                AssetType.OPTION,
                right=OptionRight.CALL,
                strike=Decimal("110"),
                expiry=date.today(),
                multiplier=100,
            ),
            side=OrderSide.BUY,
            ratio=1,
        ),
    ]
    trade = ComboOrder(
        symbol=Symbol("AAPL"),
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        account_id="U123",
        legs=legs,
    )
    quote = Quote(symbol=Symbol("AAPL"), last=Decimal("100"))

    ctx = PortfolioContext(
        positions=[],
        balance=AccountBalance(
            "U123", Decimal("10000"), Decimal("10000"), Decimal("1000"), Decimal("1000")
        ),
    )

    result = rule.evaluate(trade, quote, ctx)
    assert result.passed


def test_max_combo_delta_rule_fail():
    rule = MaxComboDelta(max_abs_delta=20)  # Very tight limit

    # Buy 1 ATM Call (Delta 0.5 * 100 = 50)
    legs = [
        OptionLeg(
            symbol=Symbol(
                "AAPL",
                AssetType.OPTION,
                right=OptionRight.CALL,
                strike=Decimal("100"),
                expiry=date.today(),
                multiplier=100,
            ),
            side=OrderSide.BUY,
            ratio=1,
        )
    ]
    trade = ComboOrder(
        symbol=Symbol("AAPL"),
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        account_id="U123",
        legs=legs,
    )
    quote = Quote(symbol=Symbol("AAPL"), last=Decimal("100"))
    ctx = PortfolioContext(
        positions=[],
        balance=AccountBalance(
            "U123", Decimal("10000"), Decimal("10000"), Decimal("1000"), Decimal("1000")
        ),
    )

    result = rule.evaluate(trade, quote, ctx)
    assert not result.passed
    assert "exceeds max 20" in result.reason


def test_max_combo_delta_skips_stock():
    rule = MaxComboDelta(max_abs_delta=10)
    trade = MarketOrder(
        symbol=Symbol("AAPL"),
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        account_id="U123",
    )
    quote = Quote(symbol=Symbol("AAPL"), last=Decimal("100"))
    ctx = PortfolioContext(
        positions=[],
        balance=AccountBalance(
            "U123", Decimal("10000"), Decimal("10000"), Decimal("1000"), Decimal("1000")
        ),
    )

    result = rule.evaluate(trade, quote, ctx)
    assert result.passed
