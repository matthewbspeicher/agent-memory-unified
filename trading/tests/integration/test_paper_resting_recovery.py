"""Real paper matching + real Redis recovery on temporary SQLite/PostgreSQL."""

import asyncio
import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from tests.integration.test_dispatch_recovery import control, paper, service
from broker.models import (
    LimitOrder,
    StopOrder,
    StopLimitOrder,
    OrderSide,
    OrderStatus,
    Quote,
    Symbol,
    AssetType,
    TIF,
    FeeModel,
)
from broker.paper import PaperBroker
from adapters.paper.broker import SimulatedBroker
from adapters.kalshi.paper import KalshiPaperBroker
from adapters.polymarket.paper import PolymarketPaperBroker
from execution.service import ExecutionUnavailable, ExecutionRejected

pytestmark = pytest.mark.integration


def make_rig(paper, control, venue="primary", fee_model=None):
    price = D("0.6") if venue in {"kalshi", "polymarket"} else D(100)
    symbol = Symbol(
        "TEST",
        AssetType.PREDICTION if venue in {"kalshi", "polymarket"} else AssetType.STOCK,
    )
    quotes = SimpleNamespace(
        get_quote=AsyncMock(
            side_effect=lambda s: Quote(s, bid=price, ask=price, last=price)
        ),
        get_order_book=AsyncMock(return_value={}),
    )
    if venue == "primary":
        broker = PaperBroker(
            paper, market_data=quotes, max_slippage=0, fee_model=fee_model
        )
    elif venue == "simulated":
        broker = SimulatedBroker(paper, data_bus=quotes)
    else:
        broker = (KalshiPaperBroker if venue == "kalshi" else PolymarketPaperBroker)(
            paper, market_data=quotes, slippage_cents=0
        )
    account = broker.orders.paper_account_id
    order = LimitOrder(
        symbol,
        OrderSide.BUY,
        D(6),
        account,
        time_in_force=TIF.GTC,
        limit_price=price - D("0.1"),
    )
    return broker, service(broker, control), order, quotes


async def tick(broker, order, price, size, tick_id=None):
    quote = Quote(order.symbol, bid=D(price), ask=D(price), last=D(price))
    results = await broker.orders.process_tick(
        quote, bid_size=D(size), ask_size=D(size), tick_id=tick_id or str(uuid4())
    )
    return results, quote


@pytest.mark.parametrize("venue", ["primary", "simulated", "kalshi", "polymarket"])
async def test_actual_partial_fill_restart_recovery_and_remaining_risk(
    paper, control, venue
):
    broker, svc, order, quotes = make_rig(paper, control, venue)
    await paper.ensure_account(order.account_id, 100000)
    svc._acknowledge_attempt = AsyncMock(
        side_effect=TimeoutError("lost submission reply")
    )
    with pytest.raises(ExecutionUnavailable):
        await svc.submit(broker, order.account_id, order)
    attempt = (await svc.reconciliation_status())["attempt"]
    results, quote = await tick(broker, order, order.limit_price, 2)
    assert results[0].status == OrderStatus.PARTIAL
    assert results[0].filled_quantity == 2
    # Recreate broker and execution service over the persisted ledger.
    broker2, recovered_service, _, quotes2 = make_rig(paper, control, venue)
    await control.set("kill_switch:active", "true")
    await recovered_service.recover(attempt["token"])
    journal = json.loads(await control.get("execution:admission:reservations"))
    assert len(journal) == 1
    state = await broker2.account.get_risk_state(order.account_id)
    assert state.context.daily_trade_count == 1
    assert state.orders[0].filled_quantity == 2
    assert state.context.positions[0].quantity == 2
    assert state.context.balance.cash == D(100000) - 2 * order.limit_price
    await control.set("kill_switch:active", "false")
    extra = deepcopy(order)
    extra.quantity = D(5)
    assert not (
        await recovered_service.preview(broker2, order.account_id, extra)
    ).passed
    extra.quantity = D(4)
    assert (await recovered_service.preview(broker2, order.account_id, extra)).passed
    result, _ = await tick(broker2, order, order.limit_price, 4)
    assert result[0].status == OrderStatus.FILLED
    state = await broker2.account.get_risk_state(order.account_id)
    assert not state.orders
    assert state.context.positions[0].quantity == 6
    assert state.context.daily_trade_count == 1


async def test_partial_amendment_lost_reply_recovers_real_terms(paper, control):
    broker, svc, order, quotes = make_rig(paper, control)
    accepted = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, order.limit_price, 2)
    svc._acknowledge_attempt = AsyncMock(side_effect=TimeoutError("lost amend reply"))
    with pytest.raises(ExecutionUnavailable):
        await svc.amend(
            broker, accepted.order_id, {"quantity": D(8), "limit_price": D(98)}
        )
    attempt = (await svc.reconciliation_status())["attempt"]
    await control.set("kill_switch:active", "true")
    await service(broker, control).recover(attempt["token"])
    state = await broker.account.get_risk_state("PAPER")
    assert state.orders[0].order.quantity == 8
    assert state.orders[0].order.limit_price == 98
    assert state.orders[0].filled_quantity == 2
    await tick(broker, order, D(98), 6)
    result = await paper.get_order_result(accepted.order_id)
    assert result.filled_quantity == 8
    assert result.status == OrderStatus.FILLED
    assert (await broker.account.get_risk_state("PAPER")).context.daily_trade_count == 1


async def test_fenced_late_amendment_preserves_existing_order(paper, control):
    broker, svc, order, quotes = make_rig(paper, control)
    accepted = await svc.submit(broker, "PAPER", order)
    original = broker.orders.modify_order
    broker.orders.modify_order = AsyncMock(
        side_effect=RuntimeError("amend rolled back")
    )
    with pytest.raises(ExecutionUnavailable):
        await svc.amend(broker, accepted.order_id, {"quantity": D(8)})
    broker.orders.modify_order = original
    attempt = (await svc.reconciliation_status())["attempt"]
    await control.set("kill_switch:active", "true")
    await svc.recover(attempt["token"])
    result = await broker.orders.amend_dispatch(
        accepted.order_id, {"quantity": D(8)}, attempt["dispatch_id"], attempt["epoch"]
    )
    assert result.status == OrderStatus.REJECTED
    assert (await paper.get_order_snapshot(accepted.order_id)).order.quantity == 6


async def test_fifo_finite_liquidity_and_concurrent_tick_replay(paper, control):
    broker, svc, order, quotes = make_rig(paper, control)
    order.quantity = D(3)
    first = await svc.submit(broker, "PAPER", order)
    second = await svc.submit(broker, "PAPER", order)
    quote = Quote(
        order.symbol,
        bid=order.limit_price,
        ask=order.limit_price,
        last=order.limit_price,
    )

    async def apply():
        return await broker.orders.process_tick(
            quote, bid_size=D(0), ask_size=D(4), tick_id="same-tick"
        )

    one, two = await asyncio.gather(apply(), apply())
    assert one == two
    assert (await paper.get_order_result(first.order_id)).filled_quantity == 3
    assert (await paper.get_order_result(second.order_id)).filled_quantity == 1
    assert (await broker.account.get_risk_state("PAPER")).context.positions[
        0
    ].quantity == 4
    with pytest.raises(ValueError, match="different data"):
        await broker.orders.process_tick(
            quote, bid_size=D(0), ask_size=D(5), tick_id="same-tick"
        )


async def test_tick_failure_rolls_back_fills_and_can_retry(paper, control):
    broker, svc, order, quotes = make_rig(paper, control)
    accepted = await svc.submit(broker, "PAPER", order)
    original = paper.save_order
    paper.save_order = AsyncMock(side_effect=RuntimeError("after ledger fill"))
    quote = Quote(
        order.symbol,
        bid=order.limit_price,
        ask=order.limit_price,
        last=order.limit_price,
    )
    with pytest.raises(RuntimeError):
        await broker.orders.process_tick(
            quote, bid_size=D(0), ask_size=D(2), tick_id="retry"
        )
    paper.save_order = original
    state = await broker.account.get_risk_state("PAPER")
    assert not state.context.positions
    assert state.orders[0].filled_quantity == 0
    await broker.orders.process_tick(
        quote, bid_size=D(0), ask_size=D(2), tick_id="retry"
    )
    assert (await paper.get_order_result(accepted.order_id)).filled_quantity == 2


async def test_cancel_partial_and_halt_bulk_cancel_preserve_fills(paper, control):
    broker, svc, order, quotes = make_rig(paper, control)
    accepted = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, order.limit_price, 2)
    await control.set("kill_switch:active", "true")
    result = await broker.orders.cancel_order(accepted.order_id)
    assert result.status == OrderStatus.CANCELLED
    assert result.filled_quantity == 2
    assert await broker.orders.cancel_order(accepted.order_id) == result
    assert not (await tick(broker, order, order.limit_price, 100))[0]
    state = await broker.account.get_risk_state("PAPER")
    assert not state.orders
    assert state.context.positions[0].quantity == 2
    await control.set("kill_switch:active", "false")
    accepted2 = await svc.submit(broker, "PAPER", order)
    svc._risk.register_brokers({"paper": broker})
    assert await svc._risk.set_halted(True) == []
    assert (
        await broker.orders.get_order_status(accepted2.order_id)
        == OrderStatus.CANCELLED
    )


async def test_stop_limit_trigger_persists_and_day_order_expires(paper, control):
    broker, svc, limit, quotes = make_rig(paper, control)
    stop = StopLimitOrder(
        limit.symbol,
        OrderSide.BUY,
        D(2),
        "PAPER",
        time_in_force=TIF.GTC,
        stop_price=D(110),
        limit_price=D(105),
    )
    accepted = await svc.submit(broker, "PAPER", stop)
    assert not (await tick(broker, stop, 111, 2))[0]
    # Trigger remains latched even when the market moves back below the stop.
    result, _ = await tick(broker, stop, 104, 1)
    assert result[0].status == OrderStatus.PARTIAL
    await tick(broker, stop, 104, 1)
    assert await broker.orders.get_order_status(accepted.order_id) == OrderStatus.FILLED
    day = deepcopy(limit)
    day.time_in_force = TIF.DAY
    accepted_day = await svc.submit(broker, "PAPER", day)
    async with paper.transaction() as db:
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        await db.execute(
            "UPDATE paper_order_terms SET submitted_at=? WHERE order_id=?",
            (yesterday, accepted_day.order_id),
        )
    result, _ = await tick(broker, day, day.limit_price, 6)
    assert result[0].status == OrderStatus.CANCELLED
    assert result[0].filled_quantity == 0


async def test_partial_fees_and_weighted_average(paper, control):
    class Fee(FeeModel):
        def calculate(self, order, price):
            return order.quantity * D("0.25")

    broker, svc, order, quotes = make_rig(paper, control, fee_model=Fee())
    accepted = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, 99, 2)
    await tick(broker, order, 96, 4)
    result = await paper.get_order_result(accepted.order_id)
    assert result.avg_fill_price == 97
    assert result.commission == D("1.5")
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.balance.cash == D("99416.5")
    assert state.context.daily_pnl == D("-1.5")
    assert state.context.daily_trade_count == 1


async def test_tick_predating_acceptance_cannot_fill_new_order(paper, control):
    broker, svc, order, _ = make_rig(paper, control)
    quote = Quote(order.symbol, bid=D(99), ask=D(99), last=D(99))
    accepted = await svc.submit(broker, "PAPER", order)
    assert (
        await broker.orders.process_tick(
            quote, bid_size=D(6), ask_size=D(6), tick_id=str(uuid4())
        )
        == []
    )
    assert (await paper.get_order_result(accepted.order_id)).filled_quantity == 0


@pytest.mark.parametrize("invalid", ["negative", "nan", "stale", "crossed", "naive"])
async def test_invalid_ticks_leave_resting_order_unchanged(paper, control, invalid):
    broker, svc, order, _ = make_rig(paper, control)
    accepted = await svc.submit(broker, "PAPER", order)
    quote = Quote(order.symbol, bid=D(99), ask=D(99), last=D(99))
    size = D(6)
    if invalid == "negative":
        size = D(-1)
    elif invalid == "nan":
        size = D("NaN")
    elif invalid == "stale":
        quote = replace(quote, timestamp=quote.timestamp - timedelta(minutes=1))
    elif invalid == "crossed":
        quote = replace(quote, bid=D(100))
    else:
        quote = replace(quote, timestamp=quote.timestamp.replace(tzinfo=None))
    with pytest.raises(ValueError):
        await broker.orders.process_tick(
            quote, bid_size=size, ask_size=size, tick_id=str(uuid4())
        )
    assert (await paper.get_order_result(accepted.order_id)).filled_quantity == 0


async def test_sell_partial_fills_and_ioc_rejection(paper, control):
    broker, svc, order, _ = make_rig(paper, control)
    order.side = OrderSide.SELL
    order.limit_price = D(101)
    order.time_in_force = TIF.IOC
    assert (await svc.submit(broker, "PAPER", order)).status == OrderStatus.REJECTED
    order.time_in_force = TIF.GTC
    accepted = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, 102, 2)
    await tick(broker, order, 103, 4)
    result = await paper.get_order_result(accepted.order_id)
    assert result.status == OrderStatus.FILLED
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.positions[0].quantity == -6
    assert state.context.balance.cash == D(100616)


async def test_stop_limit_trigger_at_submission_is_durable(paper, control):
    broker, svc, order, _ = make_rig(paper, control)
    stop = StopLimitOrder(
        order.symbol,
        OrderSide.BUY,
        D(2),
        "PAPER",
        time_in_force=TIF.GTC,
        stop_price=D(99),
        limit_price=D(98),
    )
    accepted = await svc.submit(broker, "PAPER", stop)
    assert accepted.status == OrderStatus.SUBMITTED
    results, _ = await tick(broker, stop, 97, 2)
    assert results[0].status == OrderStatus.FILLED


async def test_same_provider_tick_can_reach_multiple_accounts(paper, control):
    tick_id = str(uuid4())
    for venue in ("kalshi", "polymarket"):
        broker, svc, order, _ = make_rig(paper, control, venue)
        await paper.ensure_account(order.account_id, 100000)
        await svc.submit(broker, order.account_id, order)
        results, _ = await tick(broker, order, order.limit_price, 2, tick_id)
        assert results[0].filled_quantity == 2


async def test_completed_order_racing_amend_is_definite_rejection(paper, control):
    broker, svc, order, _ = make_rig(paper, control)
    accepted = await svc.submit(broker, "PAPER", order)
    original = broker.orders.amend_dispatch

    async def race(*args, **kwargs):
        await tick(broker, order, order.limit_price, 6)
        return await original(*args, **kwargs)

    broker.orders.amend_dispatch = race
    result = await svc.amend(broker, accepted.order_id, {"quantity": D(7)})
    assert result.status == OrderStatus.REJECTED
    assert await control.get("execution:admission:lock") is None
    assert (
        await paper.get_order_result(accepted.order_id)
    ).status == OrderStatus.FILLED


async def test_fractional_partial_quantity_survives_persisted_snapshot(paper, control):
    broker, svc, order, _ = make_rig(paper, control)
    order.quantity = D("0.3")
    accepted = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, 99, D("0.1"))
    assert (await broker.account.get_risk_state("PAPER")).orders[
        0
    ].filled_quantity == D("0.1")
    await tick(broker, order, 98, D("0.2"))
    assert (await paper.get_order_result(accepted.order_id)).filled_quantity == D("0.3")
    assert (await broker.account.get_risk_state("PAPER")).context.positions[
        0
    ].quantity == D("0.3")


async def test_day_expiry_uses_clock_and_covers_other_symbols(paper, control):
    broker, svc, order, _ = make_rig(paper, control)
    order.time_in_force = TIF.DAY
    accepted = await svc.submit(broker, "PAPER", order)
    db = await paper._get_db()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    async with paper.transaction():
        await db.execute(
            "UPDATE paper_order_terms SET submitted_at=? WHERE order_id=?",
            (yesterday, accepted.order_id),
        )
        await db.execute(
            "UPDATE paper_orders SET created_at=? WHERE order_id=?",
            (yesterday, accepted.order_id),
        )
    other = deepcopy(order)
    other.symbol = Symbol("OTHER")
    results, _ = await tick(broker, other, 99, 6)
    assert results[0].order_id == accepted.order_id
    assert results[0].status == OrderStatus.CANCELLED
    assert results[0].filled_quantity == 0
