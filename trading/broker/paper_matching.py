"""Persisted resting orders driven by explicit, idempotent liquidity ticks.

Immediate marketable orders retain their existing simulation path. Ticks supply
finite bid/ask liquidity; quote.volume is never treated as executable depth.
"""

import json
import uuid
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from broker.models import (
    OrderResult,
    OrderStatus,
    OrderSide,
    LimitOrder,
    StopOrder,
    StopLimitOrder,
    TIF,
    is_stale,
    timestamp_age_seconds,
)
from broker.order_terms import validate_order_terms

_OPEN = {OrderStatus.SUBMITTED, OrderStatus.PARTIAL}


class PaperOrderMustRest(ValueError):
    """The order cannot fill at this quote but could later.

    stop_triggered says whether a stop-limit's stop has already been hit, so
    the order rests as a plain limit from here on.
    """

    def __init__(self, message: str, *, stop_triggered: bool) -> None:
        super().__init__(message)
        self.stop_triggered = stop_triggered


class PaperMatchingMixin:
    paper_account_id = "PAPER"

    @property
    def store(self):
        """The Paper ledger this order manager writes to."""
        return self._store

    async def order_snapshot(self, order_id):
        return await self._snapshot(order_id)

    async def place_order(self, account_id, order):
        order = deepcopy(order)
        validate_order_terms(account_id, order)
        if account_id != self.paper_account_id:
            return OrderResult(
                "", OrderStatus.REJECTED, message="Paper account mismatch"
            )
        if order.time_in_force == TIF.GTD:
            return OrderResult(
                "", OrderStatus.REJECTED, message="GTD requires an expiry model"
            )
        from storage.unit_of_work import PaperWriteNotStarted

        try:
            async with self._store.transaction():
                must_rest = None
                try:
                    result = await self._place_immediate_order(account_id, order)
                except PaperOrderMustRest as exc:
                    must_rest = exc
                    result = OrderResult("", OrderStatus.REJECTED, message=str(exc))
                resting = must_rest is not None
                if resting and order.time_in_force in {TIF.DAY, TIF.GTC}:
                    result = OrderResult(str(uuid.uuid4()), OrderStatus.SUBMITTED)
                    await self._store.save_order(
                        result.order_id,
                        account_id,
                        order.symbol,
                        order.side,
                        order.quantity,
                        result.status.value,
                        Decimal(0),
                        None,
                    )
                if result.order_id and result.status != OrderStatus.REJECTED:
                    await self._store.save_order_terms(result.order_id, order)
                    if resting and must_rest.stop_triggered:
                        await self._store.set_stop_triggered(result.order_id, True)
                return result
        except PaperWriteNotStarted as exc:
            return OrderResult("", OrderStatus.REJECTED, message=str(exc))

    async def _snapshot(self, order_id):
        snap = await self._store.get_order_snapshot(order_id)
        if snap is None or snap.order.account_id != self.paper_account_id:
            raise ValueError("Unknown paper order")
        return snap

    async def modify_order(self, order_id, changes):
        if not changes or set(changes) - {"quantity", "limit_price", "stop_price"}:
            raise ValueError("Unsupported amendment fields")
        async with self._store.transaction():
            snap = await self._snapshot(order_id)
            if snap.status not in _OPEN:
                return OrderResult(
                    "", OrderStatus.REJECTED, message="Paper order is not open"
                )
            order = deepcopy(snap.order)
            for key, value in changes.items():
                if not hasattr(order, key):
                    raise ValueError("Amendment field does not apply to order")
                setattr(order, key, value)
            validate_order_terms(order.account_id, order)
            if order.quantity <= snap.filled_quantity:
                return OrderResult(
                    "",
                    OrderStatus.REJECTED,
                    message="Amended quantity must exceed fills",
                )
            result = await self._store.get_order_result(order_id)
            await self._store.save_order(
                order_id,
                order.account_id,
                order.symbol,
                order.side,
                order.quantity,
                result.status.value,
                result.filled_quantity,
                result.avg_fill_price,
            )
            await self._store.save_order_terms(order_id, order)
            if "stop_price" in changes:
                await self._store.set_stop_triggered(order_id, False)
            return await self._store.get_order_result(order_id)

    async def cancel_order(self, order_id):
        async with self._store.transaction():
            snap = await self._snapshot(order_id)
            result = await self._store.get_order_result(order_id)
            if snap.status in _OPEN:
                await self._store.save_order(
                    order_id,
                    snap.order.account_id,
                    snap.order.symbol,
                    snap.order.side,
                    snap.order.quantity,
                    OrderStatus.CANCELLED.value,
                    result.filled_quantity,
                    result.avg_fill_price,
                )
            return await self._store.get_order_result(order_id)

    async def get_order_status(self, order_id):
        return (await self._snapshot(order_id)).status

    async def cancel_all_orders(self):
        async with self._store.transaction():
            for order_id in await self._store.open_order_ids(self.paper_account_id):
                await self.cancel_order(order_id)

    async def expire_orders(self):
        """Expire account DAY orders from the UTC clock without market data."""
        async with self._store.transaction():
            results = []
            today = datetime.now(timezone.utc).date()
            for order_id in await self._store.open_order_ids(self.paper_account_id):
                snapshot = await self._snapshot(order_id)
                if (
                    snapshot.order.time_in_force == TIF.DAY
                    and snapshot.submitted_at.date() < today
                ):
                    results.append(await self.cancel_order(snapshot.order_id))
            return results

    async def process_tick(self, quote, *, bid_size, ask_size, tick_id):
        """Apply finite liquidity once, FIFO, to existing orders for this account.

        tick_id must uniquely identify a provider event. Replaying it returns the
        original result even after a restart. DAY means UTC calendar day here.
        """
        if not isinstance(tick_id, str) or not tick_id:
            raise ValueError("Tick identity required")
        if quote.timestamp.tzinfo is None or quote.timestamp.utcoffset() is None:
            raise ValueError("Matching tick requires a timezone")
        tick_id = json.dumps([self.paper_account_id, tick_id])
        age = timestamp_age_seconds(quote.timestamp)
        sizes = {}
        for side, value in ((OrderSide.BUY, ask_size), (OrderSide.SELL, bid_size)):
            if isinstance(value, bool):
                raise ValueError("Invalid liquidity")
            size = Decimal(str(value))
            if not size.is_finite() or size < 0:
                raise ValueError("Invalid liquidity")
            sizes[side] = size
        for price in (quote.bid, quote.ask):
            if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
                raise ValueError("Invalid matching quote")
        if quote.bid > quote.ask:
            raise ValueError("Crossed matching quote")
        request = json.dumps(
            {
                "account": self.paper_account_id,
                "quote": asdict(quote),
                "bid_size": str(sizes[OrderSide.SELL]),
                "ask_size": str(sizes[OrderSide.BUY]),
            },
            default=str,
            sort_keys=True,
        )
        async with self._store.transaction():
            generation = await self._store.account_generation(self.paper_account_id)
            if not generation:
                raise ValueError("Paper account not initialized")
            request = json.dumps(
                {"request": request, "epoch": generation}, sort_keys=True
            )
            payload = await self._store.get_match_tick(tick_id)
            if payload is not None:
                if payload["request"] != request:
                    raise ValueError("Tick identity reused with different data")
                return [
                    self._dispatch_result({"result_payload": json.dumps(r)})
                    for r in payload["results"]
                ]
            if is_stale(age):
                raise ValueError("Stale matching tick")
            results = []
            for order_id, already_triggered in await self._store.open_orders_by_arrival(
                self.paper_account_id
            ):
                snap = await self._snapshot(order_id)
                order = snap.order
                if (
                    order.time_in_force == TIF.DAY
                    and snap.submitted_at.date() < datetime.now(timezone.utc).date()
                ):
                    results.append(await self.cancel_order(snap.order_id))
                    continue
                if quote.timestamp < snap.submitted_at or order.symbol != quote.symbol:
                    continue
                price = quote.ask if order.side == OrderSide.BUY else quote.bid
                if (
                    isinstance(order, (StopOrder, StopLimitOrder))
                    and not already_triggered
                ):
                    triggered = (
                        price >= order.stop_price
                        if order.side == OrderSide.BUY
                        else price <= order.stop_price
                    )
                    if not triggered:
                        continue
                    await self._store.set_stop_triggered(snap.order_id, True)
                if isinstance(order, (LimitOrder, StopLimitOrder)):
                    if (order.side == OrderSide.BUY and price > order.limit_price) or (
                        order.side == OrderSide.SELL and price < order.limit_price
                    ):
                        continue
                take = min(sizes[order.side], order.quantity - snap.filled_quantity)
                if take <= 0:
                    continue
                fill_order = deepcopy(order)
                fill_order.quantity = take
                model = getattr(self, "_fee_model", None)
                # Persisted fill evidence, rather than rounded order averages or
                # process-local counters, is the fee basis across retries/restarts.
                fills = await self._store.fill_evidence(snap.order_id)
                filled_quantity = sum(
                    (Decimal(f["quantity"]) for f in fills), Decimal(0)
                )
                filled_notional = sum(
                    (Decimal(f["quantity"]) * Decimal(f["price"]) for f in fills),
                    Decimal(0),
                )
                paid = sum((Decimal(f["commission"]) for f in fills), Decimal(0))
                if filled_quantity != snap.filled_quantity:
                    raise ValueError("Incomplete commission fill evidence")
                commission = (
                    model.calculate_incremental(
                        fill_order,
                        price,
                        filled_quantity=filled_quantity,
                        filled_notional=filled_notional,
                        commission_paid=paid,
                    )
                    if model
                    else Decimal(0)
                )
                if not commission.is_finite() or commission < 0:
                    raise ValueError("Invalid fill commission")
                result = await self._store.record_simulated_fill(
                    str(uuid.uuid4()), snap.order_id, order, take, price, commission
                )
                sizes[order.side] -= take
                results.append(result)
            await self._store.save_match_tick(
                tick_id, {"request": request, "results": [asdict(r) for r in results]}
            )
            return results
