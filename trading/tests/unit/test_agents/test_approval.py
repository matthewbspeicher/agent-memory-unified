"""Approving a suggested Opportunity executes it once, and only while it is fresh."""

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest
from fastapi import HTTPException

from agents.approval import ApprovalRefused, OpportunityApprover
from agents.models import ActionLevel, Opportunity, OpportunityStatus
from agents.router import ConsensusRouter, OpportunityRouter
from api.routes.opportunities import _approve_and_execute, _reject_pending
from broker.models import (
    AccountBalance,
    AssetType,
    LimitOrder,
    MarketOrder,
    OrderResult,
    OrderSide,
    OrderStatus,
    Quote,
    Symbol,
    TIF,
)
from broker.order_terms import order_payload
from execution.context import AccountRiskState
from execution.service import ExecutionService
from risk.engine import RiskEngine
from risk.kill_switch import KillSwitch
from risk.rules import MaxDailyLoss, MaxDailyTrades, PortfolioContext
from storage.db import init_db
from storage.opportunities import ORDER_TERMS_KEY, REVISION_KEY, OpportunityStore
from tests.execution_controls import AdmissionLuaDouble

SYMBOL = Symbol("MKT", AssetType.PREDICTION)
ORDER = LimitOrder(
    SYMBOL,
    OrderSide.BUY,
    Decimal("5"),
    "KALSHI_PAPER",
    TIF.GTC,
    "sig-1",
    limit_price=Decimal("0.42"),
)


def opportunity(id="opp-1", trade=ORDER, expires_at=None):
    return Opportunity(
        id=id,
        agent_name="suggester",
        symbol=SYMBOL,
        signal="MISPRICED",
        confidence=0.8,
        reasoning="test",
        data={"edge": 0.07},
        timestamp=datetime.now(timezone.utc),
        suggested_trade=deepcopy(trade),
        expires_at=expires_at,
        broker_id="kalshi_paper",
    )


@pytest.fixture
async def store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield OpportunityStore(db)
    await db.close()


async def offer(store, opp):
    """Save an Opportunity the way the router does for a suggest_trade Agent."""
    await store.save(opp)
    await store.mark_approvable(opp.id, revision=opp.data.get(REVISION_KEY))


async def offered(store, ago, id="opp-1"):
    """Move the time the Opportunity was offered into the past."""
    data = json.loads((await store.get(id))["data"])
    data["approvable"] = (datetime.now(timezone.utc) - ago).isoformat()
    await store._db.execute(
        "UPDATE opportunities SET data = ? WHERE id = ?", (json.dumps(data), id)
    )


class FakeRouter:
    """Stands in for the router: records the call and sets the final status."""

    def __init__(self, store, final=OpportunityStatus.EXECUTED, error=None):
        self.store, self.final, self.error = store, final, error
        self.executed = []

    async def execute(self, opportunity, *, max_quantity=None):
        self.executed.append(opportunity)
        self.max_quantity = max_quantity
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        if self.final is not None:
            await self.store.update_status(opportunity.id, self.final)


def approver(store, router, minutes=60):
    return OpportunityApprover(store, router, max_age=timedelta(minutes=minutes))


async def status_of(store, id="opp-1"):
    return (await store.get(id))["status"]


# --- What is stored ---


async def test_exact_order_terms_survive_storage(store):
    await offer(store, opportunity())
    loaded = await store.load("opp-1")
    assert loaded.suggested_trade == ORDER
    assert (loaded.symbol, loaded.broker_id) == (SYMBOL, "kalshi_paper")
    assert loaded.data["edge"] == 0.07


async def test_expiry_survives_storage_as_the_same_instant(store):
    expiry = datetime(2026, 11, 12, 21, 30, tzinfo=timezone(timedelta(hours=9)))
    await store.save(opportunity(expires_at=expiry))
    assert (await store.load("opp-1")).expires_at == expiry


async def test_expiry_is_bound_as_a_datetime_once_the_database_refuses_text():
    """asyncpg refuses text for a TIMESTAMP column before sending anything."""

    class DataError(Exception):
        pass

    class Cursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def fetchone(self):
            return ("opp-1",)

    class TimestampColumn:
        def __init__(self):
            self.bound = []

        def execute(self, sql, params):
            self.bound.append(params[8])
            if isinstance(params[8], str):
                raise DataError(
                    "invalid input for query argument $9: '2026-11-12T21:30:00+09:00'"
                    " (expected a datetime.date or datetime.datetime instance, got 'str')"
                )
            return Cursor()

        async def commit(self):
            pass

    db = TimestampColumn()
    store = OpportunityStore(db)
    expiry = datetime(2026, 11, 12, 21, 30, tzinfo=timezone(timedelta(hours=9)))
    assert await store.save(opportunity(expires_at=expiry)) is True
    assert await store.save(opportunity(expires_at=expiry)) is True
    # Text once, then naive UTC, and no further attempt as text.
    assert db.bound == [expiry.isoformat()] + [datetime(2026, 11, 12, 12, 30)] * 2

    # Saves that all start before the first refusal each recover on their own.
    db = TimestampColumn()
    refuse = db.execute

    def after_a_round_trip(sql, params):
        class Prepared(Cursor):
            async def __aenter__(self):
                await asyncio.sleep(0)
                refuse(sql, params)
                return self

        return Prepared()

    db.execute = after_a_round_trip
    store = OpportunityStore(db)
    results = await asyncio.gather(
        *(store.save(opportunity(expires_at=expiry)) for _ in range(3))
    )
    assert results == [True, True, True]


async def test_a_refusal_of_another_argument_is_not_taken_for_the_expiry():
    class DataError(Exception):
        pass

    class Refuses:
        def __init__(self):
            self.calls = 0

        def execute(self, sql, params):
            self.calls += 1
            raise DataError(
                "invalid input for query argument $6: datetime.datetime(2026, 1, 1)"
                " (expected str, got datetime)"
            )

    db = Refuses()
    store = OpportunityStore(db)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    with pytest.raises(DataError):
        await store.save(opportunity(expires_at=expiry))
    assert db.calls == 1
    assert store._expiry_is_timestamp is False


async def test_another_database_error_is_not_retried():
    class Refuses:
        def __init__(self):
            self.calls = 0

        def execute(self, sql, params):
            self.calls += 1
            raise RuntimeError("connection lost")

    db = Refuses()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    with pytest.raises(RuntimeError):
        await OpportunityStore(db).save(opportunity(expires_at=expiry))
    assert db.calls == 1


async def test_transition_changes_status_only_from_the_expected_one(store):
    await offer(store, opportunity())
    pending, approved = OpportunityStatus.PENDING, OpportunityStatus.APPROVED
    assert await store.transition("opp-1", pending, approved) is True
    assert await store.transition("opp-1", pending, approved) is False
    assert await status_of(store) == "approved"


async def test_float_prices_are_stored_as_the_decimal_the_agent_meant(store):
    as_float = deepcopy(ORDER)
    as_float.limit_price, as_float.quantity = 57 / 100.0, 0.1
    await offer(store, opportunity(trade=as_float))
    loaded = (await store.load("opp-1")).suggested_trade
    assert (loaded.limit_price, loaded.quantity) == (Decimal("0.57"), Decimal("0.1"))


async def test_agent_data_cannot_supply_the_order(store):
    big = deepcopy(ORDER)
    big.quantity = Decimal("999")
    forged = json.loads(order_payload(big))  # complete, valid terms
    opp = opportunity(trade=None)
    opp.data = {
        "order_terms": forged,
        "approvable": datetime.now(timezone.utc).isoformat(),
        "exit": {"fraction": 1},
        "broker_id": "somewhere_else",
    }
    await store.save(opp)
    loaded = await store.load("opp-1")
    assert loaded.suggested_trade is None
    assert loaded.is_exit is False
    assert loaded.broker_id == "kalshi_paper"
    assert await store.is_approvable("opp-1") is False


async def test_agent_data_cannot_change_the_broker_after_the_offer(store):
    await offer(store, opportunity())
    await store.update_data("opp-1", {"broker_id": "somewhere_else"})
    assert (await store.load("opp-1")).broker_id == "kalshi_paper"


async def test_rerouting_a_rejected_opportunity_makes_it_pending_and_unoffered(store):
    await offer(store, opportunity())
    await store.update_status("opp-1", OpportunityStatus.REJECTED)
    assert await store.save(opportunity()) is True
    assert await status_of(store) == "pending"
    assert await store.is_approvable("opp-1") is False


@pytest.mark.parametrize(
    "status",
    [
        OpportunityStatus.APPROVED,
        OpportunityStatus.EXECUTED,
        OpportunityStatus.RECONCILIATION_REQUIRED,
    ],
)
async def test_router_does_not_route_an_id_that_was_acted_on(store, status):
    await offer(store, opportunity())
    await store.update_status("opp-1", status)
    router = OpportunityRouter(store=store, notifier=AsyncMock())
    router._try_execute = AsyncMock()
    await router.route(opportunity(), ActionLevel.AUTO_EXECUTE)
    router._try_execute.assert_not_awaited()
    assert await status_of(store) == status.value


async def test_order_terms_for_another_instrument_are_not_an_order(store):
    await offer(store, opportunity())
    await store._db.execute("UPDATE opportunities SET symbol = 'OTHER'")
    assert (await store.load("opp-1")).suggested_trade is None


async def test_unreadable_order_terms_are_not_an_order(store):
    await offer(store, opportunity())
    await store._db.execute(
        "UPDATE opportunities SET data = json_set(data, ?, json(?))",
        (f"$.{ORDER_TERMS_KEY}", '{"type": "LimitOrder"}'),
    )
    assert (await store.load("opp-1")).suggested_trade is None


async def test_exit_flag_and_fraction_survive_storage(store):
    closing = opportunity()
    closing.is_exit, closing._exit_fraction = True, 0.5
    await offer(store, closing)
    loaded = await store.load("opp-1")
    assert (loaded.is_exit, loaded._exit_fraction) == (True, 0.5)


async def test_rewriting_agent_data_keeps_what_the_store_owns(store):
    await offer(store, opportunity())
    await store.update_data("opp-1", {"note": "calibrated", "order_terms": "forged"})
    loaded = await store.load("opp-1")
    assert loaded.suggested_trade == ORDER
    assert loaded.data["note"] == "calibrated"
    assert await store.is_approvable("opp-1") is True


async def test_rerouting_an_acted_on_opportunity_does_not_make_it_pending_again(store):
    await offer(store, opportunity())
    await approver(store, FakeRouter(store)).approve("opp-1")
    await offer(store, opportunity())  # the Agent emits the same id again
    assert await status_of(store) == "executed"
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "not_pending"
    assert router.executed == []


async def test_rerouting_a_pending_opportunity_replaces_it_and_needs_a_new_offer(store):
    await offer(store, opportunity())
    changed = deepcopy(ORDER)
    changed.limit_price = Decimal("0.40")
    await store.save(opportunity(trade=changed))
    assert (await store.load("opp-1")).suggested_trade.limit_price == Decimal("0.40")
    assert await store.is_approvable("opp-1") is False


# --- Approval ---


@pytest.mark.parametrize("change", ["quantity", "broker", "nothing visible"])
async def test_approval_is_refused_when_the_offer_is_not_the_one_shown(store, change):
    await offer(store, opportunity())
    shown = await store.offered_at("opp-1")
    replacement = opportunity()
    if change == "quantity":
        replacement.suggested_trade.quantity = Decimal("500")
    if change == "broker":
        replacement.broker_id = "polymarket_paper"
    await offer(store, replacement)
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1", shown_offer=shown)
    assert refused.value.reason == "changed"
    assert router.executed == []
    assert await status_of(store) == "pending"


async def test_approval_of_the_offer_shown_executes_it(store):
    await offer(store, opportunity())
    shown = await store.offered_at("opp-1")
    router = FakeRouter(store)
    await approver(store, router).approve("opp-1", shown_offer=shown)
    assert len(router.executed) == 1


async def test_order_replaced_while_being_claimed_is_not_executed(store):
    await offer(store, opportunity())
    bigger = deepcopy(ORDER)
    bigger.quantity = Decimal("500")
    claim = store.transition

    async def replaced_just_before_the_claim(*args, **kwargs):
        store.transition = claim
        await offer(store, opportunity(trade=bigger))
        return await claim(*args, **kwargs)

    store.transition = replaced_just_before_the_claim
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "changed"
    assert router.executed == []
    assert await status_of(store) == "pending"


async def test_opportunity_never_offered_for_approval_is_refused(store):
    await store.save(opportunity())  # e.g. a notify-only Agent, or a gate held it
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "not_approvable"
    assert await status_of(store) == "pending"
    assert router.executed == []


async def test_approval_executes_the_stored_order_and_reports_the_result(store):
    await offer(store, opportunity())
    router = FakeRouter(store)
    outcome = await approver(store, router).approve("opp-1")
    assert outcome.status == OpportunityStatus.EXECUTED
    assert [o.suggested_trade for o in router.executed] == [ORDER]
    assert router.executed[0].status == OpportunityStatus.APPROVED


async def test_a_second_approval_is_refused_and_places_no_second_order(store):
    await offer(store, opportunity())
    router = FakeRouter(store)
    subject = approver(store, router)
    await subject.approve("opp-1")
    with pytest.raises(ApprovalRefused) as refused:
        await subject.approve("opp-1")
    assert refused.value.reason == "not_pending"
    assert len(router.executed) == 1


async def test_simultaneous_approvals_execute_once(store):
    await offer(store, opportunity())
    router = FakeRouter(store)
    subject = approver(store, router)
    results = await asyncio.gather(
        subject.approve("opp-1"), subject.approve("opp-1"), return_exceptions=True
    )
    assert sum(isinstance(r, ApprovalRefused) for r in results) == 1
    assert len(router.executed) == 1


@pytest.mark.parametrize(
    "status",
    [
        OpportunityStatus.REJECTED,
        OpportunityStatus.EXECUTED,
        OpportunityStatus.APPROVED,
        OpportunityStatus.RECONCILIATION_REQUIRED,
        OpportunityStatus.EXPIRED,
    ],
)
async def test_only_a_pending_opportunity_can_be_approved(store, status):
    await offer(store, opportunity())
    await store.update_status("opp-1", status)
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "not_pending"
    assert router.executed == []


async def test_unknown_opportunity_is_not_found(store):
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, FakeRouter(store)).approve("missing")
    assert refused.value.reason == "not_found"


async def test_approval_past_its_own_expiry_is_refused_and_marked_expired(store):
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    await offer(store, opportunity(expires_at=past))
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "expired"
    assert await status_of(store) == "expired"
    assert router.executed == []


async def test_own_expiry_overrides_the_default_age(store):
    future = datetime.now(timezone.utc) + timedelta(hours=6)
    await offer(store, opportunity(expires_at=future))
    await offered(store, timedelta(hours=3))
    outcome = await approver(store, FakeRouter(store)).approve("opp-1")
    assert outcome.status == OpportunityStatus.EXECUTED


async def test_opportunity_without_expiry_goes_stale_after_the_default_age(store):
    await offer(store, opportunity())
    await offered(store, timedelta(minutes=61))
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "expired"
    assert await status_of(store) == "expired"
    assert router.executed == []


async def test_cancellation_during_the_claim_gives_the_claim_back(store):
    await offer(store, opportunity())
    claim = store.transition
    landed = asyncio.Event()

    async def slow_claim(*args, **kwargs):
        store.transition = claim
        await asyncio.sleep(0.01)
        changed = await claim(*args, **kwargs)
        landed.set()
        return changed

    store.transition = slow_claim
    router = FakeRouter(store)
    task = asyncio.ensure_future(approver(store, router).approve("opp-1"))
    await asyncio.sleep(0.005)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert landed.is_set()
    assert router.executed == []
    assert await status_of(store) == "pending"


@pytest.mark.parametrize("quantity", ["-5", "NaN", "Infinity"])
async def test_unusable_quantity_is_not_executable(store, quantity):
    negative = deepcopy(ORDER)
    negative.quantity = Decimal(quantity)
    await offer(store, opportunity(trade=negative))
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "not_executable"
    assert router.executed == []


async def test_order_replaced_between_reading_offer_and_order_is_not_executed(store):
    await offer(store, opportunity())
    bigger = deepcopy(ORDER)
    bigger.quantity = Decimal("500")
    load = store.load

    async def replaced_just_before_the_load(opportunity_id):
        store.load = load
        await offer(store, opportunity(trade=bigger))
        return await load(opportunity_id)

    store.load = replaced_just_before_the_load
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "changed"
    assert router.executed == []


async def test_suggestion_without_a_quantity_leaves_it_to_sizing(store):
    unsized = deepcopy(ORDER)
    unsized.quantity = Decimal("0")
    await offer(store, opportunity(trade=unsized))
    router = FakeRouter(store)
    await approver(store, router).approve("opp-1")
    assert router.max_quantity is None


async def test_failure_before_execution_starts_releases_the_claim(store):
    await offer(store, opportunity())
    read = store.offer_identity
    calls = []

    async def fails_after_the_claim(opportunity_id):
        calls.append(opportunity_id)
        if len(calls) == 2:
            raise asyncio.CancelledError
        return await read(opportunity_id)

    store.offer_identity = fails_after_the_claim
    router = FakeRouter(store)
    with pytest.raises(asyncio.CancelledError):
        await approver(store, router).approve("opp-1")
    assert router.executed == []
    assert await status_of(store) == "pending"


async def test_replacement_offered_while_claimed_ends_pending_and_offered(store):
    await offer(store, opportunity())
    bigger = deepcopy(ORDER)
    bigger.quantity = Decimal("500")
    claim = store.transition

    async def replaced_then_offered_around_the_claim(*args, **kwargs):
        store.transition = claim
        replacement = opportunity(trade=bigger)
        await store.save(replacement)  # the router saves...
        claimed = await claim(*args, **kwargs)
        await store.mark_approvable("opp-1", revision=replacement.data[REVISION_KEY])
        return claimed

    store.transition = replaced_then_offered_around_the_claim
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "changed"
    assert router.executed == []
    assert await status_of(store) == "pending"
    assert await store.is_approvable("opp-1") is True


async def test_approval_passes_the_approved_quantity_as_the_ceiling(store):
    await offer(store, opportunity())
    router = FakeRouter(store)
    await approver(store, router).approve("opp-1")
    assert router.max_quantity == Decimal("5")


async def test_opportunity_with_no_recorded_time_still_loads(store):
    # Only the PostgreSQL schema allows a row without a creation time.
    await offer(store, opportunity())
    stored = store.get

    async def without_times(opportunity_id):
        return {**await stored(opportunity_id), "created_at": None, "updated_at": None}

    store.get = without_times
    assert (await store.load("opp-1")).timestamp.year == 1970


async def test_opportunity_saved_without_order_terms_is_refused_and_stays_pending(
    store,
):
    await offer(store, opportunity())
    await store._db.execute(
        "UPDATE opportunities SET data = json_remove(data, ?)", (f"$.{ORDER_TERMS_KEY}",)
    )
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "not_executable"
    assert await status_of(store) == "pending"
    assert router.executed == []


async def test_opportunity_that_proposed_no_trade_is_not_executable(store):
    await offer(store, opportunity(trade=None))
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, FakeRouter(store)).approve("opp-1")
    assert refused.value.reason == "not_executable"


async def test_unexpected_failure_is_never_reported_as_rejected(store):
    await offer(store, opportunity())
    router = FakeRouter(store, error=RuntimeError("connection dropped"))
    outcome = await approver(store, router).approve("opp-1")
    assert outcome.status == OpportunityStatus.RECONCILIATION_REQUIRED
    assert await status_of(store) == "reconciliation_required"


async def test_cancellation_mid_execution_leaves_it_for_reconciliation(store):
    await offer(store, opportunity())
    router = FakeRouter(store, error=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await approver(store, router).approve("opp-1")
    assert await status_of(store) == "reconciliation_required"


async def test_router_recorded_status_is_kept_when_it_then_fails(store):
    await offer(store, opportunity())

    class RejectsThenRaises(FakeRouter):
        async def execute(self, opp, **_):
            await self.store.update_status(opp.id, OpportunityStatus.REJECTED)
            raise RuntimeError("bookkeeping failed")

    outcome = await approver(store, RejectsThenRaises(store)).approve("opp-1")
    assert outcome.status == OpportunityStatus.REJECTED


async def test_no_order_placed_is_reported_as_approved_only(store):
    await offer(store, opportunity())
    outcome = await approver(store, FakeRouter(store, final=None)).approve("opp-1")
    assert outcome.status == OpportunityStatus.APPROVED
    assert "no order was confirmed" in outcome.detail


async def test_consensus_wrapper_is_unwrapped_to_the_executing_router(store):
    await offer(store, opportunity())
    inner = FakeRouter(store)
    wrapper = ConsensusRouter(inner)
    await approver(store, wrapper).approve("opp-1")
    assert len(inner.executed) == 1


# --- The approval route ---


def request_with(approver_):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(opportunity_approver=approver_))
    )


async def test_route_returns_the_execution_outcome(store):
    await offer(store, opportunity())
    body = await _approve_and_execute(
        request_with(approver(store, FakeRouter(store))), "opp-1"
    )
    assert (body["id"], body["status"]) == ("opp-1", "executed")


@pytest.mark.parametrize(
    "reason, code",
    [
        ("not_found", 404),
        ("expired", 410),
        ("not_pending", 409),
        ("not_executable", 409),
        ("not_approvable", 409),
        ("changed", 409),
    ],
)
async def test_route_maps_each_refusal_to_a_status_code(reason, code):
    refusing = SimpleNamespace(
        approve=AsyncMock(side_effect=ApprovalRefused(reason, "why"))
    )
    with pytest.raises(HTTPException) as raised:
        await _approve_and_execute(request_with(refusing), "opp-1")
    assert (raised.value.status_code, raised.value.detail) == (code, "why")


async def test_route_is_unavailable_without_an_approver():
    with pytest.raises(HTTPException) as raised:
        await _approve_and_execute(request_with(None), "opp-1")
    assert raised.value.status_code == 503


async def test_reject_applies_only_to_a_pending_opportunity(store):
    await offer(store, opportunity())
    assert (await _reject_pending(store, "opp-1"))["status"] == "rejected"
    with pytest.raises(HTTPException) as raised:
        await _reject_pending(store, "opp-1")
    assert raised.value.status_code == 409


async def test_reject_cannot_overwrite_an_executed_opportunity(store):
    await offer(store, opportunity())
    await approver(store, FakeRouter(store)).approve("opp-1")
    with pytest.raises(HTTPException) as raised:
        await _reject_pending(store, "opp-1")
    assert raised.value.status_code == 409
    assert await status_of(store) == "executed"


async def test_reject_of_an_unknown_opportunity_is_not_found(store):
    with pytest.raises(HTTPException) as raised:
        await _reject_pending(store, "missing")
    assert raised.value.status_code == 404


# --- Approval crosses the real execution boundary ---


class ControlStore(AdmissionLuaDouble):
    def __init__(self, halted):
        self.data = {"kill_switch:active": "true" if halted else "false"}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, nx=False):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def delete(self, key):
        self.data.pop(key, None)


async def routed_for_real(store, halted=False, sizing_engine=None):
    """A suggestion routed through the real router and execution service."""
    symbol = Symbol("TEST")
    order = MarketOrder(symbol, OrderSide.BUY, Decimal(2), "paper")
    balance = AccountBalance("paper", *(Decimal(10000),) * 3, Decimal(0))
    state = AccountRiskState(
        PortfolioContext([], balance, daily_pnl=Decimal(0), daily_trade_count=0),
        datetime.now(timezone.utc),
        [],
        "isolated-test-ledger",
    )
    quote = Quote(symbol, last=Decimal(100))
    broker = SimpleNamespace(
        connection=SimpleNamespace(is_connected=lambda: True),
        account=SimpleNamespace(
            get_risk_state=AsyncMock(side_effect=lambda account: deepcopy(state))
        ),
        market_data=SimpleNamespace(get_quote=AsyncMock(return_value=quote)),
        orders=SimpleNamespace(
            place_order=AsyncMock(
                return_value=OrderResult(
                    "order-1", OrderStatus.FILLED, Decimal(2), Decimal(100)
                )
            ),
            modify_order=AsyncMock(),
        ),
    )
    risk = RiskEngine([MaxDailyLoss(1000), MaxDailyTrades(10)], KillSwitch())
    service = ExecutionService(risk, ControlStore(halted=halted))
    service.register_brokers({"test": broker})
    router = OpportunityRouter(
        store=store,
        notifier=AsyncMock(),
        risk_engine=risk,
        broker=broker,
        data_bus=SimpleNamespace(
            get_quote=AsyncMock(return_value=quote),
            get_positions=AsyncMock(return_value=[]),
            get_balances=AsyncMock(return_value=balance),
        ),
        execution_service=service,
        sizing_engine=sizing_engine,
    )
    suggested = opportunity(trade=order)
    suggested.symbol, suggested.broker_id = symbol, None
    # Routed as a suggestion, exactly as a suggest_trade Agent's would be.
    await router.route(suggested, ActionLevel.SUGGEST_TRADE)
    broker.orders.place_order.assert_not_awaited()
    return router, broker


@pytest.mark.parametrize("halted", [True, False])
async def test_approved_order_crosses_real_admission(store, halted):
    router, broker = await routed_for_real(store, halted)
    outcome = await approver(store, router).approve("opp-1")

    if halted:
        assert outcome.status == OpportunityStatus.REJECTED
        broker.orders.place_order.assert_not_awaited()
    else:
        assert outcome.status == OpportunityStatus.EXECUTED
        broker.orders.place_order.assert_awaited_once()


@pytest.mark.parametrize("sized, placed", [(500, 2), (1, 1)])
async def test_sizing_can_reduce_but_never_exceed_the_approved_quantity(
    store, sized, placed
):
    sizing = SimpleNamespace(compute_size=AsyncMock(return_value=Decimal(sized)))
    router, broker = await routed_for_real(store, sizing_engine=sizing)
    await approver(store, router).approve("opp-1")
    sizing.compute_size.assert_awaited_once()
    assert broker.orders.place_order.await_args.args[1].quantity == Decimal(placed)


async def test_a_notify_only_opportunity_routed_for_real_cannot_be_approved(store):
    router = OpportunityRouter(store=store, notifier=AsyncMock())
    await router.route(opportunity(), ActionLevel.NOTIFY)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "not_approvable"


async def test_unversioned_offer_requires_a_fresh_route_without_losing_the_row(store):
    await offer(store, opportunity())
    row = await store.get('opp-1')
    payload = json.loads(row['data'])
    del payload[REVISION_KEY]
    await store._db.execute('UPDATE opportunities SET data=? WHERE id=?', (json.dumps(payload), 'opp-1'))
    await store._db.commit()
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve('opp-1')
    assert refused.value.reason == 'not_approvable'
    assert await status_of(store) == 'pending'
    assert router.executed == []
    await offer(store, opportunity())
    assert (await approver(store, router).approve('opp-1')).status == OpportunityStatus.EXECUTED


async def test_shown_revision_refuses_a_new_offer_even_if_the_clock_repeats(store):
    first = opportunity()
    await offer(store, first)
    shown = await store.offered_at(first.id)
    replacement = opportunity()
    replacement.suggested_trade.quantity = Decimal(500)
    await offer(store, replacement)
    row = await store.get(first.id)
    payload = json.loads(row['data'])
    payload['approvable'] = shown.isoformat()
    await store._db.execute('UPDATE opportunities SET data=? WHERE id=?', (json.dumps(payload), first.id))
    await store._db.commit()
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve(first.id, shown_offer=shown, shown_revision=first.data[REVISION_KEY])
    assert refused.value.reason == 'changed'
    assert router.executed == []
    assert await status_of(store) == 'pending'


async def test_replacement_between_offer_and_load_is_refused_even_with_same_offer_time(store):
    first = opportunity()
    await offer(store, first)
    shown = await store.offered_at(first.id)
    load = store.load

    async def replace(oid):
        store.load = load
        replacement = opportunity()
        replacement.suggested_trade.quantity = Decimal(500)
        await offer(store, replacement)
        payload = json.loads((await store.get(oid))['data'])
        payload['approvable'] = shown.isoformat()
        await store._db.execute('UPDATE opportunities SET data=? WHERE id=?', (json.dumps(payload), oid))
        await store._db.commit()
        return await load(oid)

    store.load = replace
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve(first.id)
    assert refused.value.reason == 'changed'
    assert router.executed == []
    assert await status_of(store) == 'pending'


async def test_stale_expiry_cannot_expire_a_replacement(store):
    first = opportunity(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    await offer(store, first)
    transition = store.transition

    async def replace_before_expiring(*args, **kwargs):
        store.transition = transition
        await offer(store, opportunity())
        return await transition(*args, **kwargs)

    store.transition = replace_before_expiring
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve(first.id)
    assert refused.value.reason == 'changed'
    assert router.executed == []
    assert await status_of(store) == 'pending'
