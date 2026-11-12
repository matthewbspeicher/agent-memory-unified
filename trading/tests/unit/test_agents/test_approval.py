"""Approving a suggested Opportunity executes it once, and only while it is fresh."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest
from fastapi import HTTPException

from agents.approval import ApprovalRefused, OpportunityApprover
from agents.models import Opportunity, OpportunityStatus
from agents.router import ConsensusRouter, OpportunityRouter
from api.routes.opportunities import _approve_and_execute
from broker.models import (
    AccountBalance,
    AssetType,
    LimitOrder,
    MarketOrder,
    OrderSide,
    Quote,
    Symbol,
    TIF,
)
from execution.context import AccountRiskState
from execution.service import ExecutionService
from risk.engine import RiskEngine
from risk.kill_switch import KillSwitch
from risk.rules import MaxDailyLoss, MaxDailyTrades, PortfolioContext
from storage.db import init_db
from storage.opportunities import ORDER_TERMS_KEY, OpportunityStore
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


class FakeRouter:
    """Stands in for the router: records the call and sets the final status."""

    def __init__(self, store, final=OpportunityStatus.EXECUTED, error=None):
        self.store, self.final, self.error = store, final, error
        self.executed = []

    async def execute(self, opportunity):
        self.executed.append(opportunity)
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
    await store.save(opportunity())
    loaded = await store.load("opp-1")
    assert loaded.suggested_trade == ORDER
    assert (loaded.symbol, loaded.broker_id) == (SYMBOL, "kalshi_paper")
    assert loaded.data["edge"] == 0.07


async def test_transition_changes_status_only_from_the_expected_one(store):
    await store.save(opportunity())
    pending, approved = OpportunityStatus.PENDING, OpportunityStatus.APPROVED
    assert await store.transition("opp-1", pending, approved) is True
    assert await store.transition("opp-1", pending, approved) is False
    assert await status_of(store) == "approved"


# --- Approval ---


async def test_approval_executes_the_stored_order_and_reports_the_result(store):
    await store.save(opportunity())
    router = FakeRouter(store)
    outcome = await approver(store, router).approve("opp-1")
    assert outcome.status == OpportunityStatus.EXECUTED
    assert [o.suggested_trade for o in router.executed] == [ORDER]
    assert router.executed[0].status == OpportunityStatus.APPROVED


async def test_a_second_approval_is_refused_and_places_no_second_order(store):
    await store.save(opportunity())
    router = FakeRouter(store)
    subject = approver(store, router)
    await subject.approve("opp-1")
    with pytest.raises(ApprovalRefused) as refused:
        await subject.approve("opp-1")
    assert refused.value.reason == "not_pending"
    assert len(router.executed) == 1


async def test_simultaneous_approvals_execute_once(store):
    await store.save(opportunity())
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
    await store.save(opportunity())
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
    await store.save(opportunity(expires_at=past))
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "expired"
    assert await status_of(store) == "expired"
    assert router.executed == []


async def test_own_expiry_overrides_the_default_age(store):
    future = datetime.now(timezone.utc) + timedelta(hours=6)
    await store.save(opportunity(expires_at=future))
    await store._db.execute(
        "UPDATE opportunities SET created_at = datetime('now', '-3 hours')"
    )
    outcome = await approver(store, FakeRouter(store)).approve("opp-1")
    assert outcome.status == OpportunityStatus.EXECUTED


async def test_opportunity_without_expiry_goes_stale_after_the_default_age(store):
    await store.save(opportunity())
    await store._db.execute(
        "UPDATE opportunities SET created_at = datetime('now', '-61 minutes')"
    )
    router = FakeRouter(store)
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, router).approve("opp-1")
    assert refused.value.reason == "expired"
    assert await status_of(store) == "expired"
    assert router.executed == []


async def test_opportunity_saved_without_order_terms_is_refused_and_stays_pending(
    store,
):
    await store.save(opportunity())
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
    await store.save(opportunity(trade=None))
    with pytest.raises(ApprovalRefused) as refused:
        await approver(store, FakeRouter(store)).approve("opp-1")
    assert refused.value.reason == "not_executable"


async def test_failure_before_submission_leaves_it_rejected_not_approved(store):
    await store.save(opportunity())
    router = FakeRouter(store, error=RuntimeError("quote source down"))
    outcome = await approver(store, router).approve("opp-1")
    assert outcome.status == OpportunityStatus.REJECTED
    assert await status_of(store) == "rejected"


async def test_no_order_placed_is_reported_as_approved_only(store):
    await store.save(opportunity())
    outcome = await approver(store, FakeRouter(store, final=None)).approve("opp-1")
    assert outcome.status == OpportunityStatus.APPROVED
    assert "no order was placed" in outcome.detail


async def test_consensus_wrapper_is_unwrapped_to_the_executing_router(store):
    await store.save(opportunity())
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
    await store.save(opportunity())
    body = await _approve_and_execute(
        request_with(approver(store, FakeRouter(store))), "opp-1"
    )
    assert (body["id"], body["status"]) == ("opp-1", "executed")


@pytest.mark.parametrize(
    "reason, code",
    [("not_found", 404), ("expired", 410), ("not_pending", 409), ("not_executable", 409)],
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


async def test_approved_order_is_refused_by_real_admission_while_halted(store):
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
        orders=SimpleNamespace(place_order=AsyncMock(), modify_order=AsyncMock()),
    )
    risk = RiskEngine([MaxDailyLoss(1000), MaxDailyTrades(10)], KillSwitch())
    service = ExecutionService(risk, ControlStore(halted=True))
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
    )
    suggested = opportunity(trade=order)
    suggested.symbol, suggested.broker_id = symbol, None
    await store.save(suggested)

    outcome = await approver(store, router).approve("opp-1")

    assert outcome.status == OpportunityStatus.REJECTED
    broker.orders.place_order.assert_not_awaited()
