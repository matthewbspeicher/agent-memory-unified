from fastapi import APIRouter, Depends, Request
from decimal import Decimal
from typing import Annotated, Any

from api.auth import verify_api_key
from api.dependencies import get_broker, check_kill_switch
from api.identity.dependencies import require_scope, Identity
from api.schemas import OrderRequestSchema, OrderResultSchema
from broker.interfaces import Broker
from broker.models import (
    OrderBase,
    Symbol,
    AssetType,
    OrderSide,
    TIF,
    MarketOrder,
    LimitOrder,
    StopOrder,
    StopLimitOrder,
    TrailingStopOrder,
)
from storage.trade_csv import TradeCSVLogger
from utils.audit import audit_event

router = APIRouter(prefix="/orders", tags=["orders"])

_csv_logger = TradeCSVLogger()


def _build_order(req: OrderRequestSchema) -> OrderBase:
    symbol = Symbol(
        ticker=req.symbol.ticker,
        asset_type=AssetType(req.symbol.asset_type),
        exchange=req.symbol.exchange,
        currency=req.symbol.currency,
    )
    side = OrderSide(req.side)
    time_in_force = TIF(req.time_in_force)
    match req.order_type.lower():
        case "market":
            return MarketOrder(
                symbol=symbol,
                side=side,
                quantity=req.quantity,
                account_id=req.account_id,
                time_in_force=time_in_force,
            )
        case "limit":
            return LimitOrder(
                symbol=symbol,
                side=side,
                quantity=req.quantity,
                account_id=req.account_id,
                time_in_force=time_in_force,
                limit_price=req.limit_price or Decimal("0"),
            )
        case "stop":
            return StopOrder(
                symbol=symbol,
                side=side,
                quantity=req.quantity,
                account_id=req.account_id,
                time_in_force=time_in_force,
                stop_price=req.stop_price or Decimal("0"),
            )
        case "stop_limit":
            return StopLimitOrder(
                symbol=symbol,
                side=side,
                quantity=req.quantity,
                account_id=req.account_id,
                time_in_force=time_in_force,
                stop_price=req.stop_price or Decimal("0"),
                limit_price=req.limit_price or Decimal("0"),
            )
        case "trailing_stop":
            return TrailingStopOrder(
                symbol=symbol,
                side=side,
                quantity=req.quantity,
                account_id=req.account_id,
                time_in_force=time_in_force,
                trail_amount=req.trail_amount,
                trail_percent=req.trail_percent,
            )
        case _:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=400, detail=f"Unknown order type: {req.order_type}"
            )


@router.post(
    "",
    response_model=OrderResultSchema,
    dependencies=[Depends(check_kill_switch), Depends(require_scope("write:orders"))],
)
@audit_event("orders.place")
async def place_order(
    req: OrderRequestSchema,
    request: Request,
    broker: Annotated[Broker, Depends(get_broker)],
):
    order = _build_order(req)
    result = await broker.orders.place_order(req.account_id, order)

    # Log to tax CSV
    if (
        result.status.value in ("SUBMITTED", "FILLED")
        and result.avg_fill_price is not None
    ):
        side = "BUY" if order.side == OrderSide.BUY else "SELL"
        _csv_logger.log_trade(
            symbol=order.symbol.ticker,
            side=side,
            quantity=order.quantity,
            price=result.avg_fill_price,
            exchange="broker",
            order_id=result.order_id,
            mode="LIVE",
            notes=result.message or "",
        )

    return result


@router.patch(
    "/{order_id}",
    response_model=OrderResultSchema,
    dependencies=[Depends(check_kill_switch), Depends(require_scope("write:orders"))],
)
@audit_event("orders.modify")
async def modify_order(
    order_id: str,
    changes: dict[str, Any],
    request: Request,
    broker: Annotated[Broker, Depends(get_broker)],
):
    return await broker.orders.modify_order(order_id, changes)


@router.delete(
    "/{order_id}",
    response_model=OrderResultSchema,
    dependencies=[Depends(check_kill_switch), Depends(require_scope("write:orders"))],
)
@audit_event("orders.cancel")
async def cancel_order(
    order_id: str,
    request: Request,
    broker: Annotated[Broker, Depends(get_broker)],
):
    return await broker.orders.cancel_order(order_id)


@router.get("/{order_id}")
async def get_order_status(
    order_id: str,
    _: Annotated[str, Depends(verify_api_key)],
    broker: Annotated[Broker, Depends(get_broker)],
):
    status = await broker.orders.get_order_status(order_id)
    return {"order_id": order_id, "status": status.value}
