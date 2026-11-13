"""Local review qualification: actual paper ledger, Redis admission and tracking."""

import asyncio
import re
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents.approval import ApprovalRefused, OpportunityApprover
from agents.models import ActionLevel, OpportunityStatus
from agents.router import OpportunityRouter
from broker.models import MarketOrder, OrderSide, OrderStatus
from tests.integration.test_dispatch_recovery import paper, control
from tests.integration.test_paper_fill_reconciliation import projection, opportunity
from tests.integration.test_paper_resting_recovery import make_rig, tick
from whatsapp.assistant import WhatsAppAssistant

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


async def test_whatsapp_stale_capture_refuses_then_fresh_concurrent_confirmations_dispatch_once(
    projection, paper, control
):
    _, _, _, store, broker, service, order, router, approve = await rig(
        projection, paper, control
    )
    entry = opportunity(order)
    await router.route(entry, ActionLevel.SUGGEST_TRADE)
    client = SimpleNamespace(send_text=AsyncMock(), record_inbound=Mock())
    assistant = WhatsAppAssistant(
        client,
        broker,
        None,
        store,
        service._risk,
        account_id="PAPER",
        execution_service=service,
        approver=approve,
    )

    async def prompt(phone):
        await assistant.handle(phone, f"/approve {entry.id}", "prompt-" + phone)
        message = client.send_text.await_args.args[1]
        match = re.search(r"Reply \*([^*]+)\* to confirm", message)
        assert match is not None, message
        return match.group(1)

    old_revision, _ = await store.offer_identity(entry.id)
    old_token = await prompt("stale-phone")
    replacement = deepcopy(entry)
    replacement.suggested_trade.quantity = D("2")
    await router.route(replacement, ActionLevel.SUGGEST_TRADE)
    new_revision, _ = await store.offer_identity(entry.id)
    assert new_revision != old_revision
    await assistant.handle("stale-phone", old_token, "stale-confirm")
    assert "changed" in client.send_text.await_args.args[1]
    assert await paper.get_order_history("PAPER") == []
    assert (await store.load(entry.id)).status == OpportunityStatus.PENDING
    assert await control.get("execution:admission:lock") is None

    first, second = await prompt("first-phone"), await prompt("second-phone")
    await asyncio.gather(
        assistant.handle("first-phone", first, "first-confirm"),
        assistant.handle("second-phone", second, "second-confirm"),
    )
    history = await paper.get_order_history("PAPER")
    assert len(history) == 1
    assert history[0].status == OrderStatus.SUBMITTED
    snapshot = await paper.get_order_snapshot(history[0].order_id)
    assert snapshot.order.quantity == D("2")
    assert (
        await store.load(entry.id)
    ).status == OpportunityStatus.RECONCILIATION_REQUIRED


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
