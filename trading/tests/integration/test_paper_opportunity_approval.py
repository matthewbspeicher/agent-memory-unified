"""Local review qualification: actual paper ledger, Redis admission and tracking."""

import asyncio
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agents.approval import ApprovalRefused, OpportunityApprover
from agents.models import ActionLevel, OpportunityStatus
from agents.router import OpportunityRouter
from broker.models import MarketOrder, OrderSide, OrderStatus
from tests.integration.test_dispatch_recovery import paper, control
from tests.integration.test_paper_fill_reconciliation import projection, opportunity
from tests.integration.test_paper_resting_recovery import make_rig, tick

pytestmark = pytest.mark.integration


async def rig(projection, paper, control):
    worker, positions, exits, store = projection
    broker, service, order, quotes = make_rig(paper, control)
    await broker.connection.connect()
    bus = SimpleNamespace(
        get_quote=quotes.get_quote,
        get_positions=AsyncMock(return_value=[]),
        get_balances=AsyncMock(return_value=await broker.account.get_balances("PAPER")),
    )
    router = OpportunityRouter(
        store=store,
        notifier=AsyncMock(),
        risk_engine=service._risk,
        broker=broker,
        brokers={"paper": broker},
        data_bus=bus,
        execution_service=service,
        fill_reconciler=worker,
    )
    approve = OpportunityApprover(store, router, max_age=timedelta(minutes=60))
    return worker, positions, exits, store, broker, service, order, router, approve


async def test_approval_partial_entry_and_approved_exit(projection, paper, control):
    (
        worker,
        positions,
        exits,
        store,
        broker,
        service,
        order,
        router,
        approve,
    ) = await rig(projection, paper, control)
    entry = opportunity(order)
    await router.route(entry, ActionLevel.SUGGEST_TRADE)
    assert await paper.get_order_history("PAPER") == []
    result = await approve.approve(entry.id)
    assert result.status == OpportunityStatus.RECONCILIATION_REQUIRED
    history = await paper.get_order_history("PAPER")
    assert len(history) == 1
    assert history[0].status == OrderStatus.SUBMITTED
    await tick(broker, order, order.limit_price, D("0.5"))
    await worker.reconcile_once()
    pos = (await positions.list_open())[0]
    assert D(pos["remaining_quantity"]) == D(".5")
    assert pos["id"] in await exits._store.load_all()
    closing = opportunity(
        MarketOrder(order.symbol, OrderSide.SELL, D(".5"), "PAPER"), position=pos["id"]
    )
    await router.route(closing, ActionLevel.SUGGEST_TRADE)
    result = await approve.approve(closing.id)
    assert result.status == OpportunityStatus.EXECUTED
    await worker.reconcile_once()
    assert (
        await paper.get_order_result(history[0].order_id)
    ).status == OrderStatus.CANCELLED
    assert (await positions.get(pos["id"]))["status"] == "closed"
    assert pos["id"] not in await exits._store.load_all()
    assert all(p.quantity == 0 for p in await broker.account.get_positions("PAPER"))


async def test_concurrent_approval_places_one_paper_order(projection, paper, control):
    (
        worker,
        positions,
        exits,
        store,
        broker,
        service,
        order,
        router,
        approve,
    ) = await rig(projection, paper, control)
    entry = opportunity(order)
    await router.route(entry, ActionLevel.SUGGEST_TRADE)
    results = await asyncio.gather(
        *(approve.approve(entry.id) for _ in range(3)), return_exceptions=True
    )
    assert sum(isinstance(r, ApprovalRefused) for r in results) == 2
    assert len(await paper.get_order_history("PAPER")) == 1


async def test_halt_refuses_approved_paper_order(projection, paper, control):
    (
        worker,
        positions,
        exits,
        store,
        broker,
        service,
        order,
        router,
        approve,
    ) = await rig(projection, paper, control)
    entry = opportunity(order)
    await router.route(entry, ActionLevel.SUGGEST_TRADE)
    await control.set("kill_switch:active", "true")
    assert (await approve.approve(entry.id)).status == OpportunityStatus.REJECTED
    assert await paper.get_order_history("PAPER") == []


async def test_lost_ack_is_reconciliation_required_without_second_dispatch(
    projection, paper, control
):
    (
        worker,
        positions,
        exits,
        store,
        broker,
        service,
        order,
        router,
        approve,
    ) = await rig(projection, paper, control)
    entry = opportunity(order)
    await router.route(entry, ActionLevel.SUGGEST_TRADE)
    service._acknowledge_attempt = AsyncMock(side_effect=TimeoutError("lost response"))
    assert (
        await approve.approve(entry.id)
    ).status == OpportunityStatus.RECONCILIATION_REQUIRED
    with pytest.raises(ApprovalRefused):
        await approve.approve(entry.id)
    assert len(await paper.get_order_history("PAPER")) == 1
    assert await control.get("execution:admission:lock") is not None


async def test_stale_router_cannot_offer_a_notify_only_replacement(
    projection, paper, control
):
    (
        worker,
        positions,
        exits,
        store,
        broker,
        service,
        order,
        router,
        approve,
    ) = await rig(projection, paper, control)
    from storage.opportunities import OpportunityStore
    from copy import deepcopy

    old = opportunity(order)
    replacement = deepcopy(old)
    replacement.suggested_trade.quantity = D(1)
    writer = OpportunityStore(store._db)
    read = store._read_metadata

    async def replace_before_offer(oid):
        row = await read(oid)
        store._read_metadata = read
        await writer.save(replacement)  # e.g. a separate notify-only router
        return row

    store._read_metadata = replace_before_offer
    await router.route(old, ActionLevel.SUGGEST_TRADE)
    with pytest.raises(ApprovalRefused) as refused:
        await approve.approve(old.id)
    assert refused.value.reason == "not_approvable"
    assert await paper.get_order_history("PAPER") == []
    assert (await store.load(old.id)).suggested_trade.quantity == D(1)
    # A fresh legitimate route must still work.
    await router.route(replacement, ActionLevel.SUGGEST_TRADE)
    await approve.approve(replacement.id)
    assert len(await paper.get_order_history("PAPER")) == 1
    await tick(broker, order, order.limit_price, D(10))
    await worker.reconcile_once()
    assert D((await positions.list_open())[0]["entry_quantity"]) == D(1)


async def test_stale_bound_metadata_cannot_change_a_replacement_paper_fill(
    projection, paper, control
):
    (
        worker,
        positions,
        exits,
        store,
        broker,
        service,
        order,
        router,
        approve,
    ) = await rig(projection, paper, control)
    from storage.opportunities import REVISION_KEY, OpportunityStore
    from copy import deepcopy

    old = opportunity(order)
    await router.route(old, ActionLevel.SUGGEST_TRADE)
    replacement = deepcopy(old)
    replacement.suggested_trade.quantity = D(1)
    writer = OpportunityStore(store._db)
    read = store._read_metadata

    async def replace_and_offer(oid):
        row = await read(oid)
        store._read_metadata = read
        await writer.save(replacement)
        await writer.mark_approvable(oid, revision=replacement.data[REVISION_KEY])
        return row

    store._read_metadata = replace_and_offer
    assert not await store.update_data(
        old.id,
        {"confidence_calibration": {"old": True}},
        revision=old.data[REVISION_KEY],
    )
    await approve.approve(old.id)  # HTTP approves the current offer by id
    assert len(await paper.get_order_history("PAPER")) == 1
    await tick(broker, order, order.limit_price, D(10))
    await worker.reconcile_once()
    position = (await positions.list_open())[0]
    assert D(position["entry_quantity"]) == D(1)
    assert position["id"] in await exits._store.load_all()
    assert "confidence_calibration" not in (await store.load(old.id)).data
