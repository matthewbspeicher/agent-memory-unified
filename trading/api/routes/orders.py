from fastapi import APIRouter, Depends

from api.dependencies import get_current_user, require_scope
from api.deps import get_broker
from api.schemas import OrderRequestSchema, OrderResultSchema
from broker.interfaces import Broker
from broker.models import (
    Symbol, AssetType, OrderSide, TIF,
    MarketOrder, LimitOrder, StopOrder, StopLimitOrder, TrailingStopOrder,
)

router = APIRouter(prefix="/orders", tags=["orders"])


def _build_order(req: OrderRequestSchema):
    symbol = Symbol(
        ticker=req.symbol.ticker,
        asset_type=AssetType(req.symbol.asset_type),
        exchange=req.symbol.exchange,
        currency=req.symbol.currency,
    )
    base = dict(
        symbol=symbol,
        side=OrderSide(req.side),
        quantity=req.quantity,
        account_id=req.account_id,
        time_in_force=TIF(req.time_in_force),
    )
    match req.order_type.lower():
        case "market":
            return MarketOrder(**base)
        case "limit":
            return LimitOrder(**base, limit_price=req.limit_price)
        case "stop":
            return StopOrder(**base, stop_price=req.stop_price)
        case "stop_limit":
            return StopLimitOrder(**base, stop_price=req.stop_price, limit_price=req.limit_price)
        case "trailing_stop":
            return TrailingStopOrder(**base, trail_amount=req.trail_amount, trail_percent=req.trail_percent)
        case _:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Unknown order type: {req.order_type}")


@router.post("", response_model=OrderResultSchema)
async def place_order(
    req: OrderRequestSchema,
    user: dict = Depends(require_scope("trading:execute")),
    broker: Broker = Depends(get_broker),
):
    """Place a new order.

    Requires trading:execute scope for authentication.
    """
    order = _build_order(req)
    return await broker.orders.place_order(req.account_id, order)


@router.patch("/{order_id}", response_model=OrderResultSchema)
async def modify_order(
    order_id: str,
    changes: dict,
    user: dict = Depends(get_current_user),
    broker: Broker = Depends(get_broker),
):
    """Modify an existing order.

    Requires authentication via JWT or legacy token.
    """
    return await broker.orders.modify_order(order_id, changes)


@router.delete("/{order_id}", response_model=OrderResultSchema)
async def cancel_order(
    order_id: str,
    user: dict = Depends(get_current_user),
    broker: Broker = Depends(get_broker),
):
    """Cancel an existing order.

    Requires authentication via JWT or legacy token.
    """
    return await broker.orders.cancel_order(order_id)


@router.get("/{order_id}")
async def get_order_status(
    order_id: str,
    user: dict = Depends(get_current_user),
    broker: Broker = Depends(get_broker),
):
    """Get the status of an order.

    Requires authentication via JWT or legacy token.
    """
    status = await broker.orders.get_order_status(order_id)
    return {"order_id": order_id, "status": status.value}
