"""Real ledger + Redis dispatch + automatic tracked-fill reconciliation."""

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal as D
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from agents.models import Opportunity
from broker.models import OrderSide, OrderStatus, MarketOrder
from execution.fill_reconciliation import PaperFillReconciler
from execution.service import ExecutionUnavailable
from exits.manager import ExitManager
from storage.exit_rules import ExitRuleStore
from storage.opportunities import OpportunityStore
from storage.pnl import TrackedPositionStore
from storage.trades import TradeStore
from tests.integration.test_dispatch_recovery import paper, control
from tests.integration.test_paper_resting_recovery import make_rig, tick

pytestmark = pytest.mark.integration


@pytest.fixture
async def projection(paper):
    db = await paper._get_db()
    serial = (
        "SERIAL PRIMARY KEY"
        if paper._is_postgres
        else "INTEGER PRIMARY KEY AUTOINCREMENT"
    )
    await db.execute(f"""CREATE TABLE tracked_positions (
        id {serial}, agent_name TEXT NOT NULL, opportunity_id TEXT NOT NULL,
        symbol TEXT NOT NULL, side TEXT NOT NULL, entry_price TEXT NOT NULL,
        entry_quantity INTEGER NOT NULL, entry_fees TEXT NOT NULL, entry_time TEXT NOT NULL,
        expires_at TEXT, broker_id TEXT, account_id TEXT, exit_price TEXT, exit_fees TEXT,
        exit_time TEXT, exit_reason TEXT, max_adverse_excursion TEXT DEFAULT '0', status TEXT DEFAULT 'open')""")
    await db.execute("""CREATE TABLE opportunities (id TEXT PRIMARY KEY, agent_name TEXT,
        symbol TEXT, signal TEXT, confidence REAL, reasoning TEXT, suggested_trade TEXT,
        status TEXT, expires_at TEXT, data TEXT, updated_at TEXT, created_at TEXT)""")
    await db.execute(
        "CREATE TABLE position_exit_rules (position_id INTEGER PRIMARY KEY, rules_json TEXT NOT NULL)"
    )
    await db.execute(
        f"CREATE TABLE trade_executions (id {serial}, opportunity_id TEXT, order_result TEXT, risk_evaluation TEXT, agent_name TEXT, created_at TEXT)"
    )
    await db.commit()
    positions = TrackedPositionStore(db)
    exits = ExitManager(ExitRuleStore(db))
    opps = OpportunityStore(db)
    worker = PaperFillReconciler(
        paper, positions, opps, exits, trade_store=TradeStore(db)
    )
    await worker.initialize()
    try:
        yield worker, positions, exits, opps
    finally:
        await positions.close()
        if hasattr(exits._store, "close"):
            await exits._store.close()


def opportunity(order, *, position=None):
    return Opportunity(
        id=uuid4().hex,
        timestamp=datetime.now(timezone.utc),
        agent_name="test",
        symbol=order.symbol,
        signal="test",
        confidence=1,
        reasoning="test",
        suggested_trade=order,
        is_exit=position is not None,
        data={"tracked_position_id": position} if position else {},
    )


async def submit(worker, opps, svc, broker, opp):
    await opps.save(opp)
    order = await worker.register(opp, broker)
    return await svc.submit(broker, order.account_id, order)


async def test_partial_entry_restart_partial_exit_and_cancel(
    projection, paper, control
):
    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control)
    order.quantity = D("1.5")
    opp = opportunity(order)
    accepted = await submit(worker, opps, svc, broker, opp)
    await tick(broker, order, 99, D(".5"))
    await worker.reconcile_once()
    position = (await positions.list_open())[0]
    pid = position["id"]
    assert D(position["entry_quantity"]) == D(".5")
    assert D(position["remaining_quantity"]) == D(".5")
    assert await positions.has_pending_execution(pid)
    assert pid in await exits._store.load_all()
    # Restart worker, repeat evidence, then complete entry.
    restarted = PaperFillReconciler(paper, positions, opps, ExitManager(exits._store))
    await restarted.initialize()
    await restarted.reconcile_once()
    assert len(await positions.list_open()) == 1
    await tick(broker, order, 98, D("1"))
    await restarted.reconcile_once()
    assert not await positions.has_pending_execution(pid)
    assert D((await positions.get(pid))["entry_quantity"]) == D("1.5")
    exit_order = type(order)(
        order.symbol,
        OrderSide.SELL,
        D("1.5"),
        order.account_id,
        limit_price=D(101),
        time_in_force=order.time_in_force,
    )
    exit_opp = opportunity(exit_order, position=pid)
    closing = await submit(restarted, opps, svc, broker, exit_opp)
    await tick(broker, exit_order, 102, D(".25"))
    await restarted.reconcile_once()
    position = await positions.get(pid)
    assert position["status"] == "open"
    assert D(position["remaining_quantity"]) == D("1.25")
    assert pid in await exits._store.load_all()
    await broker.orders.cancel_order(closing.order_id)
    await restarted.reconcile_once()
    assert not await positions.has_pending_execution(pid)
    assert D((await positions.get(pid))["remaining_quantity"]) == D("1.25")
    exit_order.quantity = D("1.25")
    await submit(restarted, opps, svc, broker, opportunity(exit_order, position=pid))
    await tick(broker, exit_order, 103, D("1.25"))
    await restarted.reconcile_once()
    assert (await positions.get(pid))["status"] == "closed"
    assert pid not in await exits._store.load_all()
    assert await positions.list_open() == []


async def test_lost_dispatch_response_still_projects_fill(projection, paper, control):
    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control)
    svc._acknowledge_attempt = AsyncMock(side_effect=TimeoutError("lost reply"))
    with pytest.raises(ExecutionUnavailable):
        await submit(worker, opps, svc, broker, opportunity(order))
    await tick(broker, order, 99, 2)
    await worker.reconcile_once()
    assert D((await positions.list_open())[0]["remaining_quantity"]) == 2
    assert await control.get(
        "execution:admission:lock"
    )  # Projection never unlocks execution.


async def test_projection_failure_after_fill_commit_retries_without_duplicates(
    projection, paper, control
):
    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control)
    await submit(worker, opps, svc, broker, opportunity(order))
    await tick(broker, order, 99, 6)
    original = exits.reconcile_position
    exits.reconcile_position = AsyncMock(side_effect=RuntimeError("projection failure"))
    await worker.reconcile_once()
    assert len(await positions.list_open()) == 1
    exits.reconcile_position = original
    await worker.reconcile_once()
    await worker.reconcile_once()
    assert len(await positions.list_open()) == 1
    assert D((await positions.list_open())[0]["entry_quantity"]) == 6


async def test_automatic_worker_projects_without_manual_poll(
    projection, paper, control
):
    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control)
    await submit(worker, opps, svc, broker, opportunity(order))
    task = asyncio.create_task(worker.run(interval=0.01))
    try:
        await tick(broker, order, 99, 2)
        async with asyncio.timeout(3):
            while not await positions.list_open():
                await asyncio.sleep(0.01)
        assert D((await positions.list_open())[0]["entry_quantity"]) == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_unfilled_cancel_creates_no_position(projection, paper, control):
    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control)
    opp = opportunity(order)
    result = await submit(worker, opps, svc, broker, opp)
    await broker.orders.cancel_order(result.order_id)
    await worker.reconcile_once()
    assert await positions.list_open() == []
    assert (await opps.get(opp.id))["status"] == "rejected"


async def test_duplicate_exit_registration_is_refused(projection, paper, control):
    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control)
    await submit(worker, opps, svc, broker, opportunity(order))
    await tick(broker, order, 99, 6)
    await worker.reconcile_once()
    pid = (await positions.list_open())[0]["id"]
    order.side, order.limit_price = OrderSide.SELL, D(101)
    await submit(worker, opps, svc, broker, opportunity(order, position=pid))
    with pytest.raises(ValueError, match="outstanding"):
        await submit(worker, opps, svc, broker, opportunity(order, position=pid))


async def test_two_workers_project_once_and_preserve_rules(projection, paper, control):
    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control)
    await submit(worker, opps, svc, broker, opportunity(order))
    await tick(broker, order, 99, 2)
    positions2 = TrackedPositionStore(await paper._get_db())
    exits2 = ExitManager(ExitRuleStore(await paper._get_db()))
    other = PaperFillReconciler(paper, positions2, opps, exits2)
    await other.initialize()
    try:
        await asyncio.gather(worker.reconcile_once(), other.reconcile_once())
        rows = await positions.list_open()
        assert len(rows) == 1
        assert D(rows[0]["entry_quantity"]) == 2
        assert rows[0]["id"] in await exits._store.load_all()
    finally:
        await positions2.close()
        await exits2._store.close()


async def test_immediate_fee_receipt_is_preserved(projection, paper, control):
    from broker.models import FeeModel

    class Fee(FeeModel):
        def calculate(self, order, fill_price):
            return D("1.25")

    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control, fee_model=Fee())
    market = MarketOrder(order.symbol, OrderSide.BUY, D("0.5"), "PAPER")
    result = await submit(worker, opps, svc, broker, opportunity(market))
    assert result.commission == D("1.25")
    await worker.reconcile_once()
    row = (await positions.list_open())[0]
    assert D(row["entry_quantity"]) == D("0.5")
    assert D(row["entry_fees"]) == D("1.25")


@pytest.mark.parametrize("immediate", [False, True])
async def test_router_uses_durable_projection_without_legacy_full_trade_hooks(
    projection, paper, control, immediate
):
    from agents.router import OpportunityRouter

    worker, positions, exits, opps = projection
    broker, svc, order, quotes = make_rig(paper, control)
    await broker.connection.connect()
    quotes.get_positions = AsyncMock(
        return_value=await broker.account.get_positions("PAPER")
    )
    quotes.get_balances = AsyncMock(
        return_value=await broker.account.get_balances("PAPER")
    )
    tracker = AsyncMock()
    router = OpportunityRouter(
        store=opps,
        notifier=AsyncMock(),
        risk_engine=svc._risk,
        broker=broker,
        brokers={"paper": broker},
        data_bus=quotes,
        execution_service=svc,
        fill_reconciler=worker,
        trade_tracker=tracker,
        exit_manager=exits,
    )
    if immediate:
        order = MarketOrder(order.symbol, order.side, order.quantity, order.account_id)
    opp = opportunity(order)
    await opps.save(opp)
    await router._try_execute(opp)
    assert (await opps.get(opp.id))["status"] == (
        "executed" if immediate else "reconciliation_required"
    )
    tracker.record_entry.assert_not_awaited()
    await tick(broker, order, 99, 2)
    await worker.reconcile_once()
    assert D((await positions.list_open())[0]["remaining_quantity"]) == (
        6 if immediate else 2
    )
    # Even a stale opportunity object cannot dispatch again after registration.
    from agents.models import OpportunityStatus

    opp.status = OpportunityStatus.PENDING
    await router._try_execute(opp)
    db = await paper._get_db()
    assert (
        await (await db.execute("SELECT COUNT(*) AS n FROM paper_orders")).fetchone()
    )["n"] == 1


async def test_reset_epoch_leaves_old_job_unprojected(projection, paper, control):
    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control)
    await submit(worker, opps, svc, broker, opportunity(order))
    await tick(broker, order, 99, 2)
    async with paper.transaction() as db:
        await db.execute(
            "UPDATE paper_risk_coverage SET generation=? WHERE account_id=?",
            (uuid4().hex, "PAPER"),
        )
    await worker.reconcile_once()
    assert await positions.list_open() == []


async def test_trade_history_updates_one_receipt_and_partial_fees(
    projection, paper, control
):
    from broker.models import FeeModel

    class Fee(FeeModel):
        def calculate(self, order, fill_price):
            return order.quantity * D(".25")

    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control, fee_model=Fee())
    opp = opportunity(order)
    await submit(worker, opps, svc, broker, opp)
    await worker.reconcile_once()
    await tick(broker, order, 99, 2)
    await worker.reconcile_once()
    await tick(broker, order, 98, 4)
    await worker.reconcile_once()
    await worker.reconcile_once()
    db = await paper._get_db()
    rows = await (
        await db.execute(
            "SELECT order_result FROM trade_executions WHERE opportunity_id=?",
            (opp.id,),
        )
    ).fetchall()
    assert len(rows) == 1
    assert D(json.loads(rows[0]["order_result"])["filled_quantity"]) == 6
    position = (await positions.list_open())[0]
    assert D(position["entry_fees"]) == D("1.5")
    assert D(position["entry_quantity"]) == 6


async def test_fenced_nonacceptance_releases_pending_projection(
    projection, paper, control
):
    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control)
    opp = opportunity(order)
    broker.orders.submit_dispatch = AsyncMock(
        side_effect=TimeoutError("before acceptance")
    )
    with pytest.raises(ExecutionUnavailable):
        await submit(worker, opps, svc, broker, opp)
    attempt = (await svc.reconciliation_status())["attempt"]
    await control.set("kill_switch:active", "true")
    await svc.recover(attempt["token"])
    await worker.reconcile_once()
    assert (await opps.get(opp.id))["status"] == "rejected"
    db = await paper._get_db()
    assert (
        await (
            await db.execute(
                "SELECT done FROM paper_fill_jobs WHERE job_id=?", (opp.id,)
            )
        ).fetchone()
    )["done"] == 1
    assert await positions.list_open() == []


async def test_reset_between_evidence_and_apply_cannot_create_stale_inventory(
    projection, paper, control
):
    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control)
    await submit(worker, opps, svc, broker, opportunity(order))
    await tick(broker, order, 99, 2)
    original = positions.apply_entry_fill

    async def race(**kwargs):
        async with paper.transaction() as db:
            await db.execute(
                "UPDATE paper_risk_coverage SET generation=? WHERE account_id=?",
                (uuid4().hex, "PAPER"),
            )
        return await original(**kwargs)

    positions.apply_entry_fill = race
    await worker.reconcile_once()
    assert await positions.list_open() == []


async def test_prediction_expiry_protection_survives_projection(
    projection, paper, control
):
    from datetime import timedelta
    from broker.models import ContractDetails

    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control, "kalshi")
    await paper.ensure_account(order.account_id, 100000)
    expiry = datetime.now(timezone.utc) + timedelta(days=5)
    broker.market_data.get_contract_details = AsyncMock(
        return_value=ContractDetails(order.symbol, expires_at=expiry)
    )
    await submit(worker, opps, svc, broker, opportunity(order))
    await tick(broker, order, order.limit_price, 6)
    await worker.reconcile_once()
    position = (await positions.list_open())[0]
    assert position["expires_at"] == expiry.isoformat()
    types = {type(rule).__name__ for rule in exits._rules[position["id"]]}
    assert {"ThetaDecayExit", "PreExpiryExit"} <= types
