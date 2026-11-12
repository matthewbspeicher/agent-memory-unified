"""Cumulative dollar admission using real paper state and real Redis."""

from copy import deepcopy
from decimal import Decimal as D
from unittest.mock import AsyncMock
import asyncio
import pytest
from broker.models import Symbol, OrderSide, OrderStatus, Quote, MarketOrder
from execution.service import ExecutionRejected, ExecutionUnavailable
from risk.rules import MaxPortfolioExposure
from tests.integration.test_dispatch_recovery import paper, control, service
from tests.integration.test_paper_resting_recovery import make_rig, tick

pytestmark = pytest.mark.integration


def rig(paper, control):
    broker, svc, order, quotes = make_rig(paper, control)
    svc._risk._rules = [MaxPortfolioExposure(0.6)]  # $600 on $100k equity
    order.quantity = D(4)
    order.limit_price = D(99)
    return broker, svc, order, quotes


async def test_multiple_symbols_reserve_dollars_and_cancel_releases(paper, control):
    broker, svc, order, _ = rig(paper, control)
    accepted = await svc.submit(broker, "PAPER", order)
    extra = deepcopy(order)
    extra.symbol = Symbol("OTHER")
    extra.quantity = D(3)
    with pytest.raises(ExecutionRejected, match="Cumulative exposure"):
        await svc.submit(broker, "PAPER", extra)
    await broker.orders.cancel_order(accepted.order_id)
    assert (await svc.submit(broker, "PAPER", extra)).status == OrderStatus.SUBMITTED


async def test_partial_fill_counts_holdings_plus_only_remaining_order(paper, control):
    broker, svc, order, _ = rig(paper, control)
    await svc.submit(broker, "PAPER", order)
    await tick(broker, order, 99, 2)
    extra = deepcopy(order)
    extra.symbol = Symbol("OTHER")
    extra.quantity = D(2)
    assert (await svc.preview(broker, "PAPER", extra)).passed
    extra.quantity = D("2.01")
    assert not (await svc.preview(broker, "PAPER", extra)).passed


async def test_amendment_replaces_own_remaining_reservation(paper, control):
    broker, svc, order, _ = rig(paper, control)
    accepted = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, 99, 2)
    assert (
        await svc.amend(broker, accepted.order_id, {"quantity": D(6)})
    ).status == OrderStatus.PARTIAL
    with pytest.raises(ExecutionRejected):
        await svc.amend(broker, accepted.order_id, {"quantity": D(7)})


async def test_pending_sell_does_not_manufacture_capacity(paper, control):
    broker, svc, order, _ = rig(paper, control)
    await svc.submit(
        broker, "PAPER", MarketOrder(order.symbol, OrderSide.BUY, D(4), "PAPER")
    )
    selling = deepcopy(order)
    selling.side = OrderSide.SELL
    selling.limit_price = D(101)
    await svc.submit(broker, "PAPER", selling)
    extra = deepcopy(order)
    extra.symbol = Symbol("OTHER")
    extra.quantity = D(3)
    with pytest.raises(ExecutionRejected):
        await svc.submit(broker, "PAPER", extra)


async def test_restart_and_lost_ack_restore_dollar_reservation(paper, control):
    broker, svc, order, _ = rig(paper, control)
    svc._acknowledge_attempt = AsyncMock(side_effect=TimeoutError("lost ack"))
    with pytest.raises(ExecutionUnavailable):
        await svc.submit(broker, "PAPER", order)
    attempt = (await svc.reconciliation_status())["attempt"]
    fresh = service(broker, control)
    fresh._risk._rules = [MaxPortfolioExposure(0.6)]
    await control.set("kill_switch:active", "true")
    await fresh.recover(attempt["token"])
    await control.set("kill_switch:active", "false")
    extra = deepcopy(order)
    extra.symbol = Symbol("OTHER")
    extra.quantity = D(3)
    assert not (await fresh.preview(broker, "PAPER", extra)).passed


async def test_concurrent_symbols_cannot_both_spend_capacity(paper, control):
    broker, svc, order, _ = rig(paper, control)
    other = deepcopy(order)
    other.symbol = Symbol("OTHER")
    outcomes = await asyncio.gather(
        svc.submit(broker, "PAPER", order),
        svc.submit(broker, "PAPER", other),
        return_exceptions=True,
    )
    assert sum(not isinstance(r, Exception) for r in outcomes) == 1


async def test_price_changes_and_missing_other_symbol_quotes_fail_closed(
    paper, control
):
    broker, svc, order, quotes = rig(paper, control)
    await svc.submit(broker, "PAPER", order)
    other = deepcopy(order)
    other.symbol = Symbol("OTHER")
    other.quantity = D(1)
    quotes.get_quote.side_effect = lambda s: Quote(
        s, bid=D(200), ask=D(200), last=D(200)
    )
    assert not (await svc.preview(broker, "PAPER", other)).passed
    quotes.get_quote.side_effect = lambda s: (
        Quote(s, bid=D(100), ask=D(100), last=D(100)) if s == other.symbol else None
    )
    with pytest.raises(ExecutionUnavailable):
        await svc.submit(broker, "PAPER", other)


async def test_amending_price_reserves_more_dollars_without_double_counting(
    paper, control
):
    broker, svc, order, _ = rig(paper, control)
    accepted = await svc.submit(broker, "PAPER", order)
    # $4 * 151 > $600, even though quantity is unchanged.
    with pytest.raises(ExecutionRejected, match="Cumulative exposure"):
        await svc.amend(broker, accepted.order_id, {"limit_price": D(151)})
    assert (await paper.get_order_snapshot(accepted.order_id)).order.limit_price == D(
        99
    )


async def test_partial_cancellation_keeps_filled_dollars_reserved(paper, control):
    broker, svc, order, _ = rig(paper, control)
    accepted = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, 99, 2)
    await broker.orders.cancel_order(accepted.order_id)
    other = deepcopy(order)
    other.symbol = Symbol("OTHER")
    other.quantity = D(4)
    assert (await svc.preview(broker, "PAPER", other)).passed
    other.quantity = D(5)
    assert not (await svc.preview(broker, "PAPER", other)).passed
