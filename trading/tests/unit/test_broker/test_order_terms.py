"""Stored Order terms are compared byte for byte during dispatch replay.

These strings are persisted in paper_order_terms and paper_dispatches. Changing
any of them makes existing records unmatchable, so they are pinned here.
"""

import json
from datetime import date
from decimal import Decimal

import pytest

from broker.models import (
    AssetType,
    LimitOrder,
    MarketOrder,
    OptionRight,
    OrderSide,
    StopLimitOrder,
    StopOrder,
    Symbol,
    TIF,
    TrailingStopOrder,
)
from broker.order_terms import (
    InvalidOrderTerms,
    decode_order,
    order_payload,
    validate_order_terms,
)


STOCK = Symbol("AAPL")
OPTION = Symbol(
    "AAPL",
    AssetType.OPTION,
    "CBOE",
    "USD",
    date(2027, 1, 15),
    Decimal("150.5"),
    OptionRight.CALL,
    100,
)
STOCK_JSON = (
    '{"asset_type": "STOCK", "currency": "USD", "exchange": null, "expiry": null, '
    '"multiplier": null, "right": null, "strike": null, "ticker": "AAPL"}'
)

PINNED = {
    "market": (
        MarketOrder(STOCK, OrderSide.BUY, Decimal("10"), "PAPER"),
        '{"data": {"account_id": "PAPER", "quantity": "10", "side": "BUY", '
        '"signal_id": null, "symbol": ' + STOCK_JSON + ', "time_in_force": "DAY"}, '
        '"type": "MarketOrder"}',
    ),
    "limit": (
        LimitOrder(
            STOCK,
            OrderSide.SELL,
            Decimal("2.5"),
            "PAPER",
            TIF.GTC,
            "sig-1",
            limit_price=Decimal("101.25"),
        ),
        '{"data": {"account_id": "PAPER", "limit_price": "101.25", "quantity": "2.5", '
        '"side": "SELL", "signal_id": "sig-1", "symbol": ' + STOCK_JSON + ", "
        '"time_in_force": "GTC"}, "type": "LimitOrder"}',
    ),
    "stop": (
        StopOrder(
            STOCK, OrderSide.SELL, Decimal("3"), "PAPER", stop_price=Decimal("95")
        ),
        '{"data": {"account_id": "PAPER", "quantity": "3", "side": "SELL", '
        '"signal_id": null, "stop_price": "95", "symbol": ' + STOCK_JSON + ", "
        '"time_in_force": "DAY"}, "type": "StopOrder"}',
    ),
    "stop_limit": (
        StopLimitOrder(
            STOCK,
            OrderSide.BUY,
            Decimal("4"),
            "PAPER",
            TIF.DAY,
            None,
            Decimal("105"),
            Decimal("106.5"),
        ),
        '{"data": {"account_id": "PAPER", "limit_price": "106.5", "quantity": "4", '
        '"side": "BUY", "signal_id": null, "stop_price": "105", "symbol": '
        + STOCK_JSON
        + ', "time_in_force": "DAY"}, "type": "StopLimitOrder"}',
    ),
    "trailing": (
        TrailingStopOrder(
            STOCK, OrderSide.SELL, Decimal("5"), "PAPER", trail_percent=Decimal("1.5")
        ),
        '{"data": {"account_id": "PAPER", "quantity": "5", "side": "SELL", '
        '"signal_id": null, "symbol": ' + STOCK_JSON + ', "time_in_force": "DAY", '
        '"trail_amount": null, "trail_percent": "1.5"}, "type": "TrailingStopOrder"}',
    ),
    "option_limit": (
        LimitOrder(
            OPTION, OrderSide.BUY, Decimal("1"), "PAPER", limit_price=Decimal("3.10")
        ),
        '{"data": {"account_id": "PAPER", "limit_price": "3.10", "quantity": "1", '
        '"side": "BUY", "signal_id": null, "symbol": {"asset_type": "OPTION", '
        '"currency": "USD", "exchange": "CBOE", "expiry": "2027-01-15", '
        '"multiplier": 100, "right": "CALL", "strike": "150.5", "ticker": "AAPL"}, '
        '"time_in_force": "DAY"}, "type": "LimitOrder"}',
    ),
}


@pytest.mark.parametrize("name", PINNED)
def test_stored_payload_is_pinned(name):
    order, expected = PINNED[name]
    assert order_payload(order) == expected


@pytest.mark.parametrize("name", PINNED)
def test_stored_payload_round_trips(name):
    order, expected = PINNED[name]
    assert decode_order(json.loads(expected)) == order


def test_numbers_stored_as_floats_are_read_as_the_decimals_they_show():
    stored = json.loads(PINNED["stop_limit"][1])
    stored["data"].update(quantity=0.1, stop_price=0.57, limit_price=1.1)
    order = decode_order(stored)
    assert (order.quantity, order.stop_price, order.limit_price) == (
        Decimal("0.1"),
        Decimal("0.57"),
        Decimal("1.1"),
    )


def test_trailing_distances_stored_as_floats_are_read_the_same_way():
    stored = json.loads(PINNED["trailing"][1])
    stored["data"].update(trail_amount=0.07, trail_percent=1.1)
    order = decode_order(stored)
    assert (order.trail_amount, order.trail_percent) == (
        Decimal("0.07"),
        Decimal("1.1"),
    )


def test_validation_normalises_in_place():
    order = LimitOrder(STOCK, OrderSide.BUY, "2", "PAPER", limit_price=3)
    validate_order_terms("PAPER", order)
    assert (order.quantity, order.limit_price) == (Decimal("2"), Decimal("3"))


@pytest.mark.parametrize(
    "account, quantity, message",
    [("OTHER", Decimal("1"), "account"), ("PAPER", Decimal("0"), "quantity")],
)
def test_invalid_terms_are_refused(account, quantity, message):
    order = MarketOrder(STOCK, OrderSide.BUY, quantity, "PAPER")
    with pytest.raises(InvalidOrderTerms, match=message):
        validate_order_terms(account, order)
