from __future__ import annotations
import asyncio
import logging
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from broker.interfaces import OrderManager
from broker.models import (
    AssetType, BracketOrder, LimitOrder, MarketOrder, OrderBase, OrderResult, OrderSide,
    OrderStatus, StopLimitOrder, StopOrder, TrailingStopOrder,
)
from adapters.tradier.client import TradierClient
from adapters.tradier.errors import TradierAPIError
from adapters.tradier._status import STATUS_MAP as _STATUS_MAP

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {"filled", "canceled", "rejected", "expired"}


class TradierOrderManager(OrderManager):

    def __init__(
        self, client: TradierClient, order_timeout: float = 10.0, poll_interval: float = 1.0,
    ) -> None:
        self._client = client
        self._order_timeout = order_timeout
        self._poll_interval = poll_interval
        self._order_callbacks: list[Callable[[OrderResult], Any]] = []

    async def place_order(self, account_id: str, order: OrderBase) -> OrderResult:
        try:
            # Reject unsupported types early with specific messages
            if isinstance(order, BracketOrder):
                return OrderResult(
                    order_id=str(uuid.uuid4()),
                    status=OrderStatus.REJECTED,
                    message="Tradier bracket orders deferred — not implemented",
                )
            if isinstance(order, TrailingStopOrder) and order.trail_percent is not None:
                return OrderResult(
                    order_id=str(uuid.uuid4()),
                    status=OrderStatus.REJECTED,
                    message="Tradier requires trail_amount, not trail_percent",
                )

            # Map order type
            price: float | None = None
            stop: float | None = None
            if isinstance(order, StopLimitOrder):
                order_type = "stop_limit"
                price = float(order.limit_price)
                stop = float(order.stop_price)
            elif isinstance(order, StopOrder):
                order_type = "stop"
                stop = float(order.stop_price)
            elif isinstance(order, TrailingStopOrder):
                # trail_amount only — trail_percent was rejected above
                order_type = "trailing_stop"
                stop = float(order.trail_amount)  # type: ignore[arg-type]
            elif isinstance(order, LimitOrder):
                order_type = "limit"
                price = float(order.limit_price)
            elif isinstance(order, MarketOrder):
                order_type = "market"
            else:
                return OrderResult(
                    order_id=str(uuid.uuid4()),
                    status=OrderStatus.REJECTED,
                    message=f"Unsupported order type: {type(order).__name__}",
                )

            side = "buy" if order.side == OrderSide.BUY else "sell"
            duration = "day"  # Phase 1 default

            # Options: build OCC symbol if applicable
            option_symbol = None
            if order.symbol.asset_type == AssetType.OPTION and order.symbol.strike:
                option_symbol = order.symbol.ticker  # Already in OCC format from agent

            raw = await self._client.place_order(
                symbol=order.symbol.ticker if not option_symbol else order.symbol.ticker.split()[0] if " " in order.symbol.ticker else order.symbol.ticker,
                side=side,
                qty=int(order.quantity),
                order_type=order_type,
                duration=duration,
                price=price,
                stop=stop,
                option_symbol=option_symbol,
            )

            order_id = str(raw.get("order", {}).get("id", ""))
            if not order_id:
                return OrderResult(
                    order_id=str(uuid.uuid4()),
                    status=OrderStatus.REJECTED,
                    message="No order ID in response",
                )

            # Poll until terminal
            return await self._poll_order(order_id)

        except TradierAPIError as e:
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
            status = raw.get("status", "").lower()
            if status in _TERMINAL_STATUSES:
                return _to_order_result(raw)

        # Past order_timeout — cancel
        logger.warning("Order %s timed out after %.0fs, cancelling", order_id, elapsed)
        try:
            await self._client.cancel_order(order_id)
        except Exception:
            pass
        return OrderResult(order_id=order_id, status=OrderStatus.CANCELLED, message="Adaptive poll timeout")

    async def modify_order(self, order_id: str, changes: dict) -> OrderResult:
        raise NotImplementedError("Tradier order modification not implemented")

    async def cancel_order(self, order_id: str) -> OrderResult:
        await self._client.cancel_order(order_id)
        return OrderResult(order_id=order_id, status=OrderStatus.CANCELLED)

    async def get_order_status(self, order_id: str) -> OrderStatus:
        raw = await self._client.get_order(order_id)
        return _STATUS_MAP.get(raw.get("status", "").lower(), OrderStatus.SUBMITTED)

    def on_order_update(self, callback: Callable[[OrderResult], Any]) -> None:
        self._order_callbacks.append(callback)

    async def cancel_all_orders(self) -> None:
        await self._client.cancel_all_orders()


def _to_order_result(raw: dict) -> OrderResult:
    return OrderResult(
        order_id=str(raw.get("id", "")),
        status=_STATUS_MAP.get(raw.get("status", "").lower(), OrderStatus.SUBMITTED),
        filled_quantity=Decimal(str(raw.get("exec_quantity", raw.get("quantity", 0)))),
        avg_fill_price=Decimal(str(raw["avg_fill_price"])) if raw.get("avg_fill_price") else None,
    )
