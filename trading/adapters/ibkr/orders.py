from decimal import Decimal

from ib_async import Order as IBOrder

from broker.models import (
    LimitOrder, MarketOrder, OrderBase, OrderResult, OrderStatus,
    StopLimitOrder, StopOrder, TrailingStopOrder,
)


def to_ib_order(order: OrderBase) -> IBOrder:
    ib = IBOrder()
    ib.action = order.side.value
    ib.totalQuantity = float(order.quantity)
    ib.tif = order.time_in_force.value
    ib.account = order.account_id

    match order:
        case MarketOrder():
            ib.orderType = "MKT"
        case LimitOrder():
            ib.orderType = "LMT"
            ib.lmtPrice = float(order.limit_price)
        case StopLimitOrder():
            ib.orderType = "STP LMT"
            ib.auxPrice = float(order.stop_price)
            ib.lmtPrice = float(order.limit_price)
        case StopOrder():
            ib.orderType = "STP"
            ib.auxPrice = float(order.stop_price)
        case TrailingStopOrder():
            ib.orderType = "TRAIL"
            if order.trail_amount is not None:
                ib.auxPrice = float(order.trail_amount)
            elif order.trail_percent is not None:
                ib.trailingPercent = float(order.trail_percent)

    return ib


_STATUS_MAP = {
    "Submitted": OrderStatus.SUBMITTED,
    "PreSubmitted": OrderStatus.SUBMITTED,
    "Filled": OrderStatus.FILLED,
    "Cancelled": OrderStatus.CANCELLED,
    "ApiCancelled": OrderStatus.CANCELLED,
    "Inactive": OrderStatus.REJECTED,
}


def to_order_result(trade) -> OrderResult:
    status = _STATUS_MAP.get(trade.orderStatus.status, OrderStatus.SUBMITTED)
    if trade.orderStatus.filled > 0 and trade.orderStatus.remaining > 0:
        status = OrderStatus.PARTIAL

    return OrderResult(
        order_id=str(trade.order.orderId),
        status=status,
        filled_quantity=Decimal(str(trade.orderStatus.filled)),
        avg_fill_price=Decimal(str(trade.orderStatus.avgFillPrice))
        if trade.orderStatus.avgFillPrice
        else None,
        message=trade.orderStatus.whyHeld or None,
    )
