"""Whether a paper order rests is a typed decision, not a matched message."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from broker.models import (
    LimitOrder,
    MarketOrder,
    OrderSide,
    Quote,
    StopLimitOrder,
    StopOrder,
    Symbol,
)
from broker.paper import executable_paper_price
from broker.paper_matching import PaperOrderMustRest

AAPL = Symbol("AAPL")


def quote(bid="99", ask="101"):
    return Quote(AAPL, Decimal(bid), Decimal(ask), Decimal("100"), 0, datetime.now(timezone.utc))


def test_marketable_limit_prices_at_the_quote():
    order = LimitOrder(AAPL, OrderSide.BUY, Decimal("1"), "PAPER", limit_price=Decimal("102"))
    assert executable_paper_price(order, quote()) == (Decimal("101"), Decimal("102"))


def test_unmarketable_limit_must_rest_untriggered():
    order = LimitOrder(AAPL, OrderSide.BUY, Decimal("1"), "PAPER", limit_price=Decimal("90"))
    with pytest.raises(PaperOrderMustRest, match="Limit is not marketable") as raised:
        executable_paper_price(order, quote())
    assert raised.value.stop_triggered is False


def test_untriggered_stop_must_rest_untriggered():
    order = StopOrder(AAPL, OrderSide.BUY, Decimal("1"), "PAPER", stop_price=Decimal("110"))
    with pytest.raises(PaperOrderMustRest, match="Stop is not triggered") as raised:
        executable_paper_price(order, quote())
    assert raised.value.stop_triggered is False


def test_triggered_stop_limit_that_is_not_marketable_rests_as_triggered():
    order = StopLimitOrder(
        AAPL, OrderSide.BUY, Decimal("1"), "PAPER",
        stop_price=Decimal("100"), limit_price=Decimal("100.5"),
    )
    with pytest.raises(PaperOrderMustRest, match="Limit is not marketable") as raised:
        executable_paper_price(order, quote())
    assert raised.value.stop_triggered is True


def test_other_refusals_are_definite_rejections():
    order = MarketOrder(AAPL, OrderSide.BUY, Decimal("1"), "PAPER")
    with pytest.raises(ValueError) as raised:
        executable_paper_price(order, None)
    assert not isinstance(raised.value, PaperOrderMustRest)
