"""Order terms: the full description of an order as accepted.

The stored payload string is persisted and compared byte for byte during
dispatch replay, so its form must not change (see tests/unit/test_broker/
test_order_terms.py).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from decimal import Decimal

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


class InvalidOrderTerms(RuntimeError):
    """The order's terms are structurally invalid; nothing was sent anywhere."""


ORDER_TYPES = {
    c.__name__: c
    for c in (MarketOrder, LimitOrder, StopOrder, StopLimitOrder, TrailingStopOrder)
}


def _decimal(value, name):
    if isinstance(value, bool):
        raise InvalidOrderTerms(f"Invalid {name}")
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise InvalidOrderTerms(f"Invalid {name}") from exc
    if not result.is_finite() or result <= 0:
        raise InvalidOrderTerms(f"Invalid {name}")
    return result


def encode_order(order):
    return {"type": type(order).__name__, "data": asdict(order)}


def decode_order(payload):
    values = payload["data"].copy()
    symbol = values.pop("symbol").copy()
    symbol["asset_type"] = AssetType(symbol["asset_type"])
    if symbol.get("expiry"):
        symbol["expiry"] = date.fromisoformat(symbol["expiry"])
    if symbol.get("strike") is not None:
        symbol["strike"] = Decimal(symbol["strike"])
    if symbol.get("right"):
        symbol["right"] = OptionRight(symbol["right"])
    values["symbol"] = Symbol(**symbol)
    values["side"] = OrderSide(values["side"])
    values["time_in_force"] = TIF(values["time_in_force"])
    for key in (
        "quantity",
        "limit_price",
        "stop_price",
        "trail_amount",
        "trail_percent",
    ):
        if values.get(key) is not None:
            # A float is read as the number it shows: Decimal(0.57) is not 0.57.
            values[key] = Decimal(str(values[key]))
    return ORDER_TYPES[payload["type"]](**values)


def order_payload(order) -> str:
    """The one stored string form of an order's terms."""
    return json.dumps(encode_order(order), default=str, sort_keys=True)


def validate_order_terms(account, order) -> None:
    """Check the terms and normalise quantity and prices to Decimal in place."""
    if (
        type(order).__name__ not in ORDER_TYPES
        or type(order) not in ORDER_TYPES.values()
    ):
        raise InvalidOrderTerms("Order type has no complete execution risk model")
    if not account or order.account_id != account:
        raise InvalidOrderTerms("Order account mismatch")
    if not isinstance(order.symbol, Symbol) or not order.symbol.ticker:
        raise InvalidOrderTerms("Invalid order symbol")
    if not isinstance(order.side, OrderSide) or not isinstance(
        order.time_in_force, TIF
    ):
        raise InvalidOrderTerms("Invalid order side or duration")
    order.quantity = _decimal(order.quantity, "quantity")
    for key in ("limit_price", "stop_price", "trail_amount", "trail_percent"):
        if hasattr(order, key) and getattr(order, key) is not None:
            setattr(order, key, _decimal(getattr(order, key), key))
    if isinstance(order, TrailingStopOrder):
        if (order.trail_amount is None) == (order.trail_percent is None):
            raise InvalidOrderTerms("Exactly one trailing distance is required")
        if order.trail_percent is not None and order.trail_percent > 100:
            raise InvalidOrderTerms("Invalid trailing percentage")
