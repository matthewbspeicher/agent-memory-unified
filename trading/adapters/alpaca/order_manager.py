from __future__ import annotations
import asyncio
import logging
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from broker.interfaces import OrderManager
from broker.models import (
    BracketOrder, LimitOrder, MarketOrder, OrderBase, OrderResult, OrderSide, OrderStatus,
    StopLimitOrder, StopOrder, TIF, TrailingStopOrder,
)
from adapters.alpaca.client import AlpacaClient
from adapters.alpaca.errors import AlpacaAPIError
from adapters.alpaca._status import STATUS_MAP as _STATUS_MAP

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {"filled", "canceled", "cancelled", "expired", "rejected"}
_SUPPORTED_ORDER_TYPES = {"market", "limit", "stop", "stop_limit", "trailing_stop"}
_SUPPORTED_TIF = {"day", "gtc"}


class AlpacaOrderManager(OrderManager):

    def __init__(
        self, client: AlpacaClient, order_timeout: float = 10.0, poll_interval: float = 1.0,
    ) -> None:
        self._client = client
        self._order_timeout = order_timeout
        self._poll_interval = poll_interval
        self._order_callbacks: list[Callable[[OrderResult], Any]] = []

    async def place_order(self, account_id: str, order: OrderBase) -> OrderResult:
        try:
            tif = order.time_in_force.value.lower()
            if tif not in _SUPPORTED_TIF:
                tif = "day"
            side = "buy" if order.side == OrderSide.BUY else "sell"
            qty = float(order.quantity)
            symbol = order.symbol.ticker

            # Map order type and build extra kwargs
            extra: dict = {}
            if isinstance(order, BracketOrder):
                order_type = order.entry_type
                if order.entry_limit_price is not None:
                    extra["limit_price"] = float(order.entry_limit_price)
                extra["order_class"] = "bracket"
                extra["take_profit"] = {"limit_price": str(order.take_profit_price)}
                stop_loss: dict = {"stop_price": str(order.stop_loss_price)}
                if order.stop_loss_limit_price is not None:
                    stop_loss["limit_price"] = str(order.stop_loss_limit_price)
                extra["stop_loss"] = stop_loss
            elif isinstance(order, StopLimitOrder):
                order_type = "stop_limit"
                extra["stop_price"] = float(order.stop_price)
                extra["limit_price"] = float(order.limit_price)
            elif isinstance(order, StopOrder):
                order_type = "stop"
                extra["stop_price"] = float(order.stop_price)
            elif isinstance(order, TrailingStopOrder):
                order_type = "trailing_stop"
                if order.trail_percent is not None:
                    extra["trail_percent"] = float(order.trail_percent)
                else:
                    extra["trail_price"] = float(order.trail_amount)  # type: ignore[arg-type]
            elif isinstance(order, LimitOrder):
                order_type = "limit"
                extra["limit_price"] = float(order.limit_price)
            elif isinstance(order, MarketOrder):
                order_type = "market"
            else:
                return OrderResult(
                    order_id=str(uuid.uuid4()),
                    status=OrderStatus.REJECTED,
                    message=f"Unsupported order type: {type(order).__name__}",
                )

            raw = await self._client.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type=order_type,
                time_in_force=tif,
                **extra,
            )

            # If already terminal, return immediately — no polling needed
            status = raw.get("status", "")
            if status in _TERMINAL_STATUSES:
                return _to_order_result(raw)

            # Poll until terminal or timeout
            return await self._poll_order(raw["id"])

        except AlpacaAPIError as e:
            return OrderResult(
                order_id=str(uuid.uuid4()),
                status=OrderStatus.REJECTED,
                message=e.message,
            )

    async def _poll_order(self, order_id: str) -> OrderResult:
        """Adaptive polling: fast interval up to phase1_limit, then slow until order_timeout."""
        elapsed = 0.0
        phase1_limit = min(10.0, self._order_timeout)
        fast_interval = self._poll_interval
        slow_interval = 30.0

        while elapsed < self._order_timeout:
            interval = fast_interval if elapsed < phase1_limit else slow_interval
            await asyncio.sleep(interval)
            elapsed += interval
            raw = await self._client.get_order(order_id)
            if raw.get("status", "") in _TERMINAL_STATUSES:
                return _to_order_result(raw)

        # Past order_timeout — cancel
        logger.warning("Order %s timed out after %.0fs, cancelling", order_id, elapsed)
        try:
            await self._client.cancel_order(order_id)
        except Exception:
            pass
        return OrderResult(order_id=order_id, status=OrderStatus.CANCELLED, message="Adaptive poll timeout")

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        raise NotImplementedError("Alpaca order modification not implemented")

    async def cancel_order(self, order_id: str) -> OrderResult:
        await self._client.cancel_order(order_id)
        return OrderResult(order_id=order_id, status=OrderStatus.CANCELLED)

    async def get_order_status(self, order_id: str) -> OrderStatus:
        raw = await self._client.get_order(order_id)
        return _STATUS_MAP.get(raw.get("status", ""), OrderStatus.SUBMITTED)

    def on_order_update(self, callback: Callable[[OrderResult], Any]) -> None:
        self._order_callbacks.append(callback)

    async def cancel_all_orders(self) -> None:
        await self._client.cancel_all_orders()


def _to_order_result(raw: dict) -> OrderResult:
    return OrderResult(
        order_id=raw["id"],
        status=_STATUS_MAP.get(raw.get("status", ""), OrderStatus.SUBMITTED),
        filled_quantity=Decimal(raw.get("filled_qty", "0")),
        avg_fill_price=Decimal(raw["filled_avg_price"]) if raw.get("filled_avg_price") else None,
    )
