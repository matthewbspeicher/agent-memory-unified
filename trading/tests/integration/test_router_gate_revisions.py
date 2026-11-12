"""Stale routing gates cannot reject a replacement or a claimed suggestion."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.models import ActionLevel, OpportunityStatus
from agents.router import OpportunityRouter
from broker.models import Quote
from execution.shadow import ShadowDecisionStatus
from storage.opportunities import REVISION_KEY
from tests.integration.test_opportunity_revisions import (
    store,
    writer,
    opportunity,
    offer,
    assert_current,
)

from tests.integration.test_dispatch_recovery import paper, control
from tests.integration.test_paper_fill_reconciliation import projection

pytestmark = pytest.mark.integration


def router_for(store, gate, before_gate=None):
    async def snapshot(symbol):
        if before_gate is not None:
            await before_gate()
        return Quote(symbol)

    router = OpportunityRouter(
        store=store,
        notifier=AsyncMock(),
        data_bus=SimpleNamespace(get_quote=AsyncMock(side_effect=snapshot)),
    )
    router._check_regime_policy = lambda opp: "blocked" if gate == "regime" else None
    router._check_htf_alignment = AsyncMock(
        return_value="blocked" if gate == "htf" else None
    )
    return router


async def evaluate_gate(router, opp, gate, before_gate=None):
    if gate == "pre_order":
        if before_gate is not None:
            await before_gate()
        assert (
            await router._finalize_pre_order_decision(
                opp,
                shadow_mode=False,
                decision_status=ShadowDecisionStatus.BLOCKED_PRECONDITION,
            )
            is True
        )  # a blocked caller must stop even if its write is stale
    else:
        await router.route(opp, ActionLevel.SUGGEST_TRADE)


@pytest.mark.parametrize("gate", ["regime", "htf", "pre_order"])
@pytest.mark.parametrize(
    "new_status",
    [
        OpportunityStatus.PENDING,
        OpportunityStatus.APPROVED,
        OpportunityStatus.RECONCILIATION_REQUIRED,
        OpportunityStatus.EXECUTED,
    ],
)
async def test_stale_gate_cannot_reject_a_replacement(store, writer, gate, new_status):
    old, replacement = opportunity(), opportunity("1")
    if gate == "pre_order":
        await store.save(old)

    async def replace():
        await offer(writer, replacement)
        if new_status != OpportunityStatus.PENDING:
            assert await writer.transition(
                replacement.id,
                OpportunityStatus.PENDING,
                new_status,
                revision=replacement.data[REVISION_KEY],
            )

    router = router_for(store, gate, replace)
    await evaluate_gate(router, old, gate, replace)
    assert (await store.get(old.id))["status"] == new_status.value
    await assert_current(store, replacement)
    assert await store.is_approvable(old.id)


@pytest.mark.parametrize("gate", ["regime", "htf", "pre_order"])
async def test_pending_gate_cannot_reject_a_claim_of_the_same_revision(
    store, writer, gate
):
    old = opportunity()
    if gate == "pre_order":
        await store.save(old)

    async def claim():
        assert await writer.transition(
            old.id,
            OpportunityStatus.PENDING,
            OpportunityStatus.APPROVED,
            revision=old.data[REVISION_KEY],
        )

    await evaluate_gate(router_for(store, gate, claim), old, gate, claim)
    assert (await store.get(old.id))["status"] == "approved"
    await assert_current(store, old)


@pytest.mark.parametrize("gate", ["regime", "htf", "pre_order"])
async def test_current_pending_gate_still_rejects_its_own_revision(store, gate):
    current = opportunity()
    if gate == "pre_order":
        await store.save(current)
    await evaluate_gate(router_for(store, gate), current, gate)
    assert (await store.get(current.id))["status"] == "rejected"
    await assert_current(store, current)


async def test_approved_execution_gate_can_reject_its_own_claim(store):
    current = opportunity()
    await offer(store, current)
    assert await store.transition(
        current.id,
        OpportunityStatus.PENDING,
        OpportunityStatus.APPROVED,
        revision=current.data[REVISION_KEY],
    )
    current.status = OpportunityStatus.APPROVED
    await evaluate_gate(router_for(store, "pre_order"), current, "pre_order")
    assert (await store.get(current.id))["status"] == "rejected"


async def test_delayed_approved_gate_preserves_a_completed_status(store):
    current = opportunity()
    await offer(store, current)
    current.status = OpportunityStatus.APPROVED
    assert await store.transition(
        current.id,
        OpportunityStatus.PENDING,
        OpportunityStatus.EXECUTED,
        revision=current.data[REVISION_KEY],
    )
    await evaluate_gate(router_for(store, "pre_order"), current, "pre_order")
    assert (await store.get(current.id))["status"] == "executed"


async def test_shadow_gate_records_without_changing_durable_status(store):
    current = opportunity()
    await offer(store, current)
    router = router_for(store, "pre_order")
    router._record_shadow_decision = AsyncMock()
    assert await router._finalize_pre_order_decision(
        current,
        shadow_mode=True,
        decision_status=ShadowDecisionStatus.BLOCKED_PRECONDITION,
    )
    router._record_shadow_decision.assert_awaited_once()
    assert (await store.get(current.id))["status"] == "pending"


@pytest.mark.parametrize("gate", ["regime", "htf", "pre_order"])
async def test_late_gate_preserves_a_replacement_partial_fill_and_exit_rules(
    projection, paper, control, gate
):
    import asyncio
    from copy import copy
    from decimal import Decimal

    from agents.approval import ApprovalRefused
    from learning.strategy_health import StrategyHealthStatus
    from tests.integration.test_paper_opportunity_approval import rig
    from tests.integration.test_paper_fill_reconciliation import (
        opportunity as paper_opportunity,
    )
    from tests.integration.test_paper_resting_recovery import tick

    worker, positions, exits, opps, broker, service, order, router, approve = await rig(
        projection, paper, control
    )
    old = paper_opportunity(order)
    replacement = deepcopy(old)
    replacement.suggested_trade.quantity = Decimal(1)
    ready, release = asyncio.Event(), asyncio.Event()
    old_router = copy(router)

    async def pause():
        ready.set()
        await release.wait()

    if gate == "pre_order":
        await opps.save(old)

        async def health_status(agent):
            await pause()
            return StrategyHealthStatus.RETIRED

        old_router._health_engine = SimpleNamespace(
            get_status=AsyncMock(side_effect=health_status)
        )
        task = asyncio.create_task(old_router._try_execute(old))
    else:

        async def quote(symbol):
            await pause()
            return Quote(symbol)

        old_router._data_bus = SimpleNamespace(get_quote=AsyncMock(side_effect=quote))
        old_router._check_regime_policy = lambda opp: (
            "blocked" if gate == "regime" else None
        )
        old_router._check_htf_alignment = AsyncMock(
            return_value="blocked" if gate == "htf" else None
        )
        task = asyncio.create_task(old_router.route(old, ActionLevel.SUGGEST_TRADE))
    try:
        async with asyncio.timeout(5):
            await ready.wait()
        await router.route(replacement, ActionLevel.SUGGEST_TRADE)
        outcome = await approve.approve(
            replacement.id, shown_revision=replacement.data[REVISION_KEY]
        )
        assert outcome.status == OpportunityStatus.RECONCILIATION_REQUIRED
        await tick(broker, order, order.limit_price, Decimal(".5"))
        await worker.reconcile_once()
        position = (await positions.list_open())[0]
        pid = position["id"]
        assert Decimal(position["remaining_quantity"]) == Decimal(".5")
        assert pid in await exits._store.load_all()
        release.set()
        await task
        assert (await opps.get(replacement.id))["status"] == "reconciliation_required"
        assert (await opps.load(replacement.id)).data[REVISION_KEY] == replacement.data[
            REVISION_KEY
        ]
        assert await opps.save(old) is False  # no path back to pending/second approval
        with pytest.raises(ApprovalRefused) as refused:
            await approve.approve(replacement.id)
        assert refused.value.reason == "not_pending"
        assert len(await paper.get_order_history("PAPER")) == 1
        await tick(broker, order, order.limit_price, Decimal(".5"))
        await worker.reconcile_once()
        final = await positions.get(pid)
        assert Decimal(final["entry_quantity"]) == Decimal(1)
        assert len(await positions.list_open()) == 1
        assert pid in await exits._store.load_all()
        assert (await opps.get(replacement.id))["status"] == "executed"
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("gate", ["regime", "htf", "pre_order"])
async def test_reusing_the_same_object_cannot_retarget_an_old_gate(store, writer, gate):
    from learning.strategy_health import StrategyHealthStatus
    from decimal import Decimal

    shared = opportunity()

    async def reuse():
        shared.suggested_trade.quantity = Decimal(1)
        await offer(writer, shared)

    router = router_for(store, gate, reuse)
    if gate == "pre_order":
        await store.save(shared)

        async def retire(agent):
            await reuse()
            return StrategyHealthStatus.RETIRED

        router._health_engine = SimpleNamespace(
            get_status=AsyncMock(side_effect=retire)
        )
        await router._try_execute(shared)
    else:
        await router.route(shared, ActionLevel.SUGGEST_TRADE)
    assert (await store.get(shared.id))["status"] == "pending"
    await assert_current(store, shared)
    assert await store.is_approvable(shared.id)
