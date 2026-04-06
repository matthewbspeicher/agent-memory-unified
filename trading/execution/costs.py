"""Execution cost computation — decision price, spread, and slippage math."""

from __future__ import annotations

from decimal import Decimal


def decision_price(
    bid: Decimal | None,
    ask: Decimal | None,
    last: Decimal | None,
) -> Decimal | None:
    """Select the best-available decision price.

    Priority:
    - midpoint when both bid and ask are present
    - last when only one side (or neither) exists
    - None when no price is available at all
    """
    if bid is not None and ask is not None:
        return (bid + ask) / Decimal("2")
    if last is not None:
        return last
    if bid is not None:
        return bid
    if ask is not None:
        return ask
    return None


def spread_bps(
    bid: Decimal | None,
    ask: Decimal | None,
    mid: Decimal | None,
) -> float | None:
    """Compute bid-ask spread in basis points.

    Returns None when bid or ask is missing (e.g. Yahoo Finance feeds).
    """
    if bid is None or ask is None or mid is None or mid == 0:
        return None
    return float((ask - bid) / mid * Decimal("10000"))


def slippage_bps(
    fill: Decimal | None,
    decision: Decimal | None,
    side: str,
) -> float | None:
    """Compute slippage in basis points.

    Positive means execution was *worse* than the decision price:
    - BUY:  fill > decision (paid more)
    - SELL: fill < decision (received less)

    Returns None when either price is unavailable.
    """
    if fill is None or decision is None or decision == 0:
        return None
    diff = fill - decision
    if side.upper() == "SELL":
        diff = -diff
    return float(diff / decision * Decimal("10000"))


def order_type_label(order_obj: object) -> str:
    """Extract a human-readable order type from an order object's class name.

    Falls back to 'unknown' when the object is None or has no class name.
    """
    if order_obj is None:
        return "unknown"
    name = type(order_obj).__name__
    # Strip trailing 'Order' suffix for cleanliness: MarketOrder -> market
    if name.endswith("Order"):
        name = name[: -len("Order")]
    return name.lower() if name else "unknown"
