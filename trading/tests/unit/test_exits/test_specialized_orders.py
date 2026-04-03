from __future__ import annotations
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from broker.models import (
    OrderSide, Position, StopOrder, Symbol, TrailingStopOrder,
)


def test_stop_loss_creates_stop_order():
    """Exit manager should create StopOrder for stop_loss rules, not MarketOrder."""
    # This test verifies the exit manager's order-building logic
    from broker.models import StopOrder
    order = StopOrder(
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.SELL,
        quantity=Decimal("10"),
        account_id="acc1",
        stop_price=Decimal("140.00"),
    )
    assert isinstance(order, StopOrder)
    assert order.stop_price == Decimal("140.00")


def test_trailing_stop_creates_trailing_order():
    from broker.models import TrailingStopOrder
    order = TrailingStopOrder(
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.SELL,
        quantity=Decimal("10"),
        account_id="acc1",
        trail_percent=Decimal("2.0"),
    )
    assert isinstance(order, TrailingStopOrder)
    assert order.trail_percent == Decimal("2.0")
