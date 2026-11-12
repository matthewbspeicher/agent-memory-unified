"""Disposable Redis + paper databases; no live adapters or market calls."""

import asyncio
import json
import os
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import aiosqlite
import asyncpg
import pytest
from redis.asyncio import Redis

from broker.models import (
    AccountBalance,
    MarketOrder,
    OrderSide,
    OrderStatus,
    OrderResult,
    Quote,
    Symbol,
    Position,
)
from broker.paper import PaperBroker
from execution.context import AccountRiskState, OrderSnapshot
from execution.dispatch import DispatchEvidence
from execution.service import (
    ExecutionService,
    ExecutionRejected,
    ExecutionUnavailable,
    _decode,
)
from risk.engine import RiskEngine
from risk.kill_switch import KillSwitch
from risk.rules import MaxPositionSize, MaxDailyTrades, PortfolioContext
from storage.paper import PaperStore
from storage.postgres import PostgresDB

pytestmark = pytest.mark.integration


class ScopedRedis:
    def __init__(self, client):
        self.client = client
        self.prefix = "test-recovery:" + uuid4().hex + ":"
        self.before_eval = None
        self.lose_reply = False

    async def get(self, key):
        return await self.client.get(self.prefix + key)

    async def set(self, key, value, **kwargs):
        return await self.client.set(self.prefix + key, value, **kwargs)

    async def delete(self, key):
        return await self.client.delete(self.prefix + key)

    async def eval(self, script, count, *args):
        recovery_script = not script.startswith("-- execution:")
        if self.before_eval and recovery_script:
            await self.before_eval()
        result = await self.client.eval(
            script, count, *[self.prefix + k for k in args[:count]], *args[count:]
        )
        if self.lose_reply and recovery_script:
            raise TimeoutError("Recovery committed but reply lost")
        return result


@pytest.fixture
async def control():
    url = os.environ["AMU_TEST_REDIS_URL"]
    client = Redis.from_url(url, decode_responses=True)
    store = ScopedRedis(client)
    await store.set("kill_switch:active", "false")
    try:
        yield store
    finally:
        keys = [k async for k in client.scan_iter(match=store.prefix + "*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()


@pytest.fixture(params=["sqlite", "postgres"])
async def paper(request, tmp_path):
    if request.param == "sqlite":
        db = await aiosqlite.connect(tmp_path / "paper.db")
        db.row_factory = aiosqlite.Row
        store = PaperStore(db)
        await store.init_tables()
        try:
            yield store
        finally:
            await store.close()
            await db.close()
    else:
        dsn = os.environ["AMU_TEST_POSTGRES_DSN"]
        schema = "recovery_" + uuid4().hex
        admin = await asyncpg.connect(dsn)
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            dsn, min_size=2, max_size=4, server_settings={"search_path": schema}
        )
        store = PaperStore(PostgresDB(pool))
        await store.init_tables()
        try:
            yield store
        finally:
            await store.close()
            await pool.close()
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()


def service(broker, control):
    risk = RiskEngine([MaxPositionSize(10000, 10), MaxDailyTrades(10)], KillSwitch())
    result = ExecutionService(risk, control)
    result.register_brokers({"paper": broker})
    return result


def paper_rig(store, control):
    quotes = SimpleNamespace(
        get_quote=AsyncMock(
            side_effect=lambda s: Quote(s, bid=D(100), ask=D(100), last=D(100))
        ),
        get_order_book=AsyncMock(return_value={}),
    )
    broker = PaperBroker(store, market_data=quotes, max_slippage=0)
    return (
        broker,
        service(broker, control),
        MarketOrder(Symbol("TEST"), OrderSide.BUY, D(6), "PAPER"),
    )


async def uncertain(svc, broker, order):
    with pytest.raises(ExecutionUnavailable, match="unknown"):
        await svc.submit(broker, "PAPER", order)
    attempt = (await svc.reconciliation_status())["attempt"]
    await svc._store.set("kill_switch:active", "true")
    return attempt


async def test_lost_response_restarts_recovers_and_replay_never_refills(paper, control):
    broker, svc, order = paper_rig(paper, control)
    svc._acknowledge_attempt = AsyncMock(side_effect=TimeoutError("reply lost"))
    attempt = await uncertain(svc, broker, order)
    restarted = service(broker, control)
    recovered = await restarted.recover(attempt["token"])
    assert recovered["recovery_outcome"] == "applied"
    assert await control.get("kill_switch:active") == "true"
    assert await control.get("execution:admission:lock") is None
    first = await broker.orders.submit_dispatch(
        "PAPER", order, attempt["dispatch_id"], attempt["epoch"]
    )
    second = await broker.orders.submit_dispatch(
        "PAPER", order, attempt["dispatch_id"], attempt["epoch"]
    )
    assert first.order_id == second.order_id
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.daily_trade_count == 1
    assert state.context.balance.cash == 99400
    with pytest.raises(ExecutionRejected):
        await restarted.recover(attempt["token"])
    different = deepcopy(order)
    different.quantity = D(1)
    with pytest.raises(ValueError, match="different order terms"):
        await broker.orders.submit_dispatch(
            "PAPER", different, attempt["dispatch_id"], attempt["epoch"]
        )


async def test_rolled_back_dispatch_is_fenced_against_late_delivery(paper, control):
    broker, svc, order = paper_rig(paper, control)
    original = paper.save_order
    paper.save_order = AsyncMock(side_effect=RuntimeError("write failure"))
    attempt = await uncertain(svc, broker, order)
    paper.save_order = original
    recovered = await svc.recover(attempt["token"])
    assert recovered["recovery_outcome"] == "not_accepted"
    result = await broker.orders.submit_dispatch(
        "PAPER", order, attempt["dispatch_id"], attempt["epoch"]
    )
    assert result.status == OrderStatus.REJECTED
    state = await broker.account.get_risk_state("PAPER")
    assert state.context.daily_trade_count == 0
    assert state.context.balance.cash == 100000


async def test_account_reset_does_not_reinterpret_old_dispatch(paper, control):
    broker, svc, order = paper_rig(paper, control)
    svc._acknowledge_attempt = AsyncMock(side_effect=TimeoutError())
    attempt = await uncertain(svc, broker, order)
    await broker.reset()
    with pytest.raises(ExecutionUnavailable):
        await svc.recover(attempt["token"])
    assert await control.get("execution:admission:lock") == attempt["token"]


class VenueOrders:
    """Authoritative deterministic venue fixture with changing open-order state."""

    def __init__(self, state, filled):
        self.state, self.filled = state, filled
        self.order = None
        self.reject_amend = False
        self.corrupt = None

    async def submit_dispatch(self, account, order, dispatch_id, epoch):
        self.order = deepcopy(order)
        self.state.orders = [
            OrderSnapshot(
                "venue-order",
                self.order,
                OrderStatus.PARTIAL if self.filled else OrderStatus.SUBMITTED,
                self.filled,
            )
        ]
        self.state.context.daily_trade_count = 1
        self.state.context.positions = (
            [Position(order.symbol, self.filled, D(100), self.filled * 100, D(0), D(0))]
            if self.filled
            else []
        )
        raise TimeoutError("venue accepted; response lost")

    async def amend_dispatch(self, oid, changes, dispatch_id, epoch):
        if not self.reject_amend:
            for key, value in changes.items():
                setattr(self.order, key, value)
            self.state.orders[0].order = deepcopy(self.order)
        raise TimeoutError("amend response lost")

    async def reconcile_dispatch(self, attempt):
        evidence = DispatchEvidence(
            attempt["dispatch_id"],
            attempt["account"],
            attempt["operation"],
            _decode(attempt["order"]),
            attempt["order_id"],
            attempt["epoch"],
            datetime.now(timezone.utc),
            "not_accepted" if self.reject_amend else "applied",
            None if self.reject_amend else deepcopy(self.state.orders[0]),
        )
        return self.corrupt(evidence) if self.corrupt else evidence


@pytest.fixture(params=[D(0), D(2)])
def venue(request, control):
    state = AccountRiskState(
        PortfolioContext(
            [],
            AccountBalance("PAPER", D(100000), D(100000), D(100000), D(0)),
            daily_pnl=D(0),
            daily_trade_count=0,
        ),
        datetime.now(timezone.utc),
        [],
        "test-venue",
        epoch="venue-generation",
    )
    orders = VenueOrders(state, request.param)
    broker = SimpleNamespace(
        orders=orders,
        account=SimpleNamespace(
            get_risk_state=AsyncMock(side_effect=lambda a: deepcopy(state))
        ),
        market_data=SimpleNamespace(
            get_quote=AsyncMock(side_effect=lambda s: Quote(s, last=D(100)))
        ),
    )
    return (
        broker,
        service(broker, control),
        MarketOrder(Symbol("TEST"), OrderSide.BUY, D(6), "PAPER"),
    )


async def test_open_partial_recovery_reconstructs_remaining_risk(venue, control):
    broker, svc, order = venue
    attempt = await uncertain(svc, broker, order)
    await svc.recover(attempt["token"])
    journal = json.loads(await control.get("execution:admission:reservations"))
    assert journal[0]["id"] == "venue-order"
    assert D(journal[0]["order"]["data"]["quantity"]) == 6
    await control.set("kill_switch:active", "false")
    order.quantity = D(5)
    assert not (await svc.preview(broker, "PAPER", order)).passed
    order.quantity = D(4)
    assert (await svc.preview(broker, "PAPER", order)).passed


@pytest.mark.parametrize("rejected", [True, False])
async def test_uncertain_amendment_rebuilds_or_preserves_original(
    venue, control, rejected
):
    broker, svc, order = venue
    attempt = await uncertain(svc, broker, order)
    await svc.recover(attempt["token"])
    await control.set("kill_switch:active", "false")
    broker.orders.reject_amend = rejected
    with pytest.raises(ExecutionUnavailable):
        await svc.amend(broker, "venue-order", {"quantity": D(8)})
    attempt = (await svc.reconciliation_status())["attempt"]
    await control.set("kill_switch:active", "true")
    await svc.recover(attempt["token"])
    journal = json.loads(await control.get("execution:admission:reservations"))
    assert len(journal) == 1
    assert D(journal[0]["order"]["data"]["quantity"]) == (6 if rejected else 8)


@pytest.mark.parametrize(
    "field,value",
    [
        ("dispatch_id", "wrong"),
        ("epoch", "wrong"),
        ("final", False),
        ("observed_at", datetime(2020, 1, 1, tzinfo=timezone.utc)),
    ],
)
async def test_invalid_provider_evidence_stays_locked(venue, control, field, value):
    broker, svc, order = venue
    attempt = await uncertain(svc, broker, order)
    broker.orders.corrupt = lambda e: replace(e, **{field: value})
    with pytest.raises(ExecutionRejected):
        await svc.recover(attempt["token"])
    assert await control.get("execution:admission:lock") == attempt["token"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("kill_switch:active", "false"),
        ("execution:admission:lock", "other"),
        ("execution:admission:attempt", "{}"),
        ("execution:admission:reservations", "[]"),
    ],
)
async def test_real_redis_cas_rejects_changed_inputs(venue, control, key, value):
    broker, svc, order = venue
    attempt = await uncertain(svc, broker, order)
    # Ensure journal has a distinct prior byte value, including the empty-list case.
    await control.set("execution:admission:reservations", "[ ]")

    async def change():
        await control.set(key, value)

    control.before_eval = change
    with pytest.raises(ExecutionRejected, match="state changed"):
        await svc.recover(attempt["token"])
    assert await control.get("execution:admission:lock") == (
        "other" if key.endswith(":lock") else attempt["token"]
    )


async def test_recovery_reply_loss_is_inspectable_and_never_resubmits(venue, control):
    broker, svc, order = venue
    attempt = await uncertain(svc, broker, order)
    control.lose_reply = True
    with pytest.raises(TimeoutError):
        await svc.recover(attempt["token"])
    status = await svc.reconciliation_status()
    assert status["attempt"]["status"] == "recovered"
    assert status["lock"] is None
    assert len(status["reservations"]) == 1


async def test_late_sender_cannot_overwrite_recovery_or_new_attempt(paper, control):
    broker, svc, order = paper_rig(paper, control)
    entered, release = asyncio.Event(), asyncio.Event()
    original = broker.orders.submit_dispatch

    async def delayed(*args):
        result = await original(*args)
        entered.set()
        await release.wait()
        return result

    broker.orders.submit_dispatch = delayed
    pending = asyncio.create_task(svc.submit(broker, "PAPER", order))
    await entered.wait()
    attempt = (await svc.reconciliation_status())["attempt"]
    await control.set("kill_switch:active", "true")
    recovery = service(broker, control)
    await recovery.recover(attempt["token"])
    # Represent a later admission owning the lock and attempt.
    await control.set("execution:admission:lock", "new-owner")
    await control.set("execution:admission:attempt", '{"token":"new-owner"}')
    before = await control.get("execution:admission:reservations")
    release.set()
    with pytest.raises(ExecutionUnavailable):
        await pending
    assert await control.get("execution:admission:lock") == "new-owner"
    assert await control.get("execution:admission:attempt") == '{"token":"new-owner"}'
    assert await control.get("execution:admission:reservations") == before
    assert (await broker.account.get_risk_state("PAPER")).context.daily_trade_count == 1


async def test_two_recovery_workers_only_one_commits(venue, control):
    broker, svc, order = venue
    attempt = await uncertain(svc, broker, order)
    second = service(broker, control)
    results = await asyncio.gather(
        svc.recover(attempt["token"]),
        second.recover(attempt["token"]),
        return_exceptions=True,
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, ExecutionRejected) for r in results) == 1
    assert len(json.loads(await control.get("execution:admission:reservations"))) == 1


async def test_legacy_terminal_recovery_script_on_real_redis(paper, control):
    broker, svc, order = paper_rig(paper, control)
    original_eval = control.eval

    async def lose_release(script, count, *args):
        if script.startswith("-- execution:release"):
            raise ConnectionError("release not sent")
        return await original_eval(script, count, *args)

    control.eval = lose_release
    await svc.submit(broker, "PAPER", order)
    control.eval = original_eval
    attempt = (await svc.reconciliation_status())["attempt"]
    await control.set("kill_switch:active", "true")
    await svc.recover_acknowledged(attempt["token"])
    assert await control.get("execution:admission:lock") is None
    assert json.loads(await control.get("execution:admission:reservations")) == []


async def test_provider_unavailable_cannot_clear_admission(venue, control):
    broker, svc, order = venue
    attempt = await uncertain(svc, broker, order)
    broker.orders.reconcile_dispatch = AsyncMock(side_effect=TimeoutError())
    with pytest.raises(ExecutionUnavailable):
        await svc.recover(attempt["token"])
    assert await control.get("execution:admission:lock") == attempt["token"]


async def test_wrong_redis_type_aborts_before_recovery_writes(venue, control):
    from redis.exceptions import ResponseError

    broker, svc, order = venue
    attempt = await uncertain(svc, broker, order)
    before = await control.get("execution:admission:attempt")

    async def corrupt():
        await control.delete("kill_switch:active")
        await control.client.rpush(control.prefix + "kill_switch:active", "true")

    control.before_eval = corrupt
    with pytest.raises(ResponseError):
        await svc.recover(attempt["token"])
    assert await control.get("execution:admission:attempt") == before
    assert await control.get("execution:admission:lock") == attempt["token"]


async def test_account_snapshot_disagreement_keeps_reservation_blocked(venue, control):
    broker, svc, order = venue
    attempt = await uncertain(svc, broker, order)
    evidence = await broker.orders.reconcile_dispatch(attempt)
    broker.orders.reconcile_dispatch = AsyncMock(return_value=evidence)
    broker.orders.state.orders[0].order = deepcopy(order)
    broker.orders.state.orders[0].order.quantity += 1
    with pytest.raises(ExecutionRejected, match="does not match"):
        await svc.recover(attempt["token"])
    assert await control.get("execution:admission:lock") == attempt["token"]
