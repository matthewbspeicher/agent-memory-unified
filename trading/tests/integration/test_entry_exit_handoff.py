"""Cancel partial paper entries before dispatching a risk-checked exit."""

from decimal import Decimal as D
from unittest.mock import AsyncMock
import pytest
from broker.models import MarketOrder, OrderSide, OrderStatus
from execution.fill_reconciliation import PaperFillReconciler
from tests.integration.test_dispatch_recovery import paper, control
from tests.integration.test_paper_fill_reconciliation import (
    projection,
    opportunity,
    submit,
)
from tests.integration.test_paper_resting_recovery import make_rig, tick

pytestmark = pytest.mark.integration


async def partial(projection, paper, control, side=OrderSide.BUY):
    worker, positions, exits, opps = projection
    broker, svc, order, quotes = make_rig(paper, control)
    order.side = side
    order.limit_price = D(101) if side == OrderSide.SELL else D(99)
    accepted = await submit(worker, opps, svc, broker, opportunity(order))
    await tick(broker, order, order.limit_price, D("0.5"))
    await worker.reconcile_once()
    pid = (await positions.list_open())[0]["id"]
    close = opportunity(
        MarketOrder(
            order.symbol,
            OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY,
            D("0.5"),
            order.account_id,
        ),
        position=pid,
    )
    return worker, positions, exits, opps, broker, svc, order, accepted, pid, close


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
async def test_cancel_then_close_only_confirmed_fill(projection, paper, control, side):
    (
        worker,
        positions,
        exits,
        opps,
        broker,
        svc,
        order,
        accepted,
        pid,
        close,
    ) = await partial(projection, paper, control, side)
    await worker.prepare_exit(close, broker, "paper")
    assert (
        await paper.get_order_result(accepted.order_id)
    ).status == OrderStatus.CANCELLED
    assert close.suggested_trade.quantity == D(".5")
    await submit(worker, opps, svc, broker, close)
    await worker.reconcile_once()
    assert (await positions.get(pid))["status"] == "closed"
    assert pid not in await exits._store.load_all()
    assert await broker.account.get_positions("PAPER") == [] or all(
        p.quantity == 0 for p in await broker.account.get_positions("PAPER")
    )


async def test_fill_racing_cancel_is_included_in_exit(projection, paper, control):
    (
        worker,
        positions,
        exits,
        opps,
        broker,
        svc,
        order,
        accepted,
        pid,
        close,
    ) = await partial(projection, paper, control)
    cancel = broker.orders.cancel_order

    async def race(oid):
        await tick(broker, order, order.limit_price, D("1.25"))
        return await cancel(oid)

    broker.orders.cancel_order = race
    await worker.prepare_exit(close, broker, "paper")
    assert close.suggested_trade.quantity == D("1.75")
    assert D((await positions.get(pid))["remaining_quantity"]) == D("1.75")
    await submit(worker, opps, svc, broker, close)
    await worker.reconcile_once()
    assert (await positions.get(pid))["status"] == "closed"


async def test_cancel_failure_blocks_exit_and_retry_after_restart(
    projection, paper, control
):
    (
        worker,
        positions,
        exits,
        opps,
        broker,
        svc,
        order,
        accepted,
        pid,
        close,
    ) = await partial(projection, paper, control)
    cancel = broker.orders.cancel_order
    broker.orders.cancel_order = AsyncMock(side_effect=TimeoutError("lost cancel"))
    with pytest.raises(TimeoutError):
        await worker.prepare_exit(close, broker, "paper")
    assert (
        await paper.get_order_result(accepted.order_id)
    ).status == OrderStatus.PARTIAL
    assert await positions.has_pending_execution(pid)
    broker.orders.cancel_order = cancel
    restarted = PaperFillReconciler(paper, positions, opps, exits)
    await restarted.prepare_exit(close, broker, "paper")
    assert not await positions.has_pending_execution(pid)
    assert close.suggested_trade.quantity == D(".5")


async def test_cancelled_entry_projection_failure_can_retry(projection, paper, control):
    (
        worker,
        positions,
        exits,
        opps,
        broker,
        svc,
        order,
        accepted,
        pid,
        close,
    ) = await partial(projection, paper, control)
    original = positions.apply_entry_fill
    positions.apply_entry_fill = AsyncMock(side_effect=RuntimeError("storage failure"))
    with pytest.raises(ValueError, match="incomplete"):
        await worker.prepare_exit(close, broker, "paper")
    assert (
        await paper.get_order_result(accepted.order_id)
    ).status == OrderStatus.CANCELLED
    positions.apply_entry_fill = original
    await worker.prepare_exit(close, broker, "paper")
    assert close.suggested_trade.quantity == D(".5")


async def test_outstanding_exit_and_wrong_account_cannot_cancel_entry(
    projection, paper, control
):
    (
        worker,
        positions,
        exits,
        opps,
        broker,
        svc,
        order,
        accepted,
        pid,
        close,
    ) = await partial(projection, paper, control)
    with pytest.raises(ValueError, match="identity"):
        await worker.prepare_exit(close, broker, "wrong")
    assert (
        await paper.get_order_result(accepted.order_id)
    ).status == OrderStatus.PARTIAL
    await worker.prepare_exit(close, broker, "paper")
    close.suggested_trade = type(order)(
        order.symbol, OrderSide.SELL, D(".5"), "PAPER", limit_price=D(101)
    )
    await submit(worker, opps, svc, broker, close)
    with pytest.raises(ValueError, match="outstanding exit"):
        await worker.prepare_exit(
            opportunity(close.suggested_trade, position=pid), broker, "paper"
        )


async def test_monitor_triggers_then_router_cancels_and_closes(
    projection, paper, control
):
    from agents.models import AgentConfig, ActionLevel
    from agents.router import OpportunityRouter
    from strategies.exit_monitor import ExitMonitorAgent
    from broker.models import Quote
    from types import SimpleNamespace

    (
        worker,
        positions,
        exits,
        opps,
        broker,
        svc,
        order,
        accepted,
        pid,
        close,
    ) = await partial(projection, paper, control)
    await broker.connection.connect()
    quotes = SimpleNamespace(
        get_quote=AsyncMock(
            side_effect=lambda symbol: Quote(symbol, bid=D(90), ask=D(90), last=D(90))
        ),
        get_positions=AsyncMock(
            return_value=await broker.account.get_positions("PAPER")
        ),
        get_balances=AsyncMock(return_value=await broker.account.get_balances("PAPER")),
    )
    config = AgentConfig(
        name="exit",
        strategy="exit_monitor",
        schedule="on_demand",
        action_level=ActionLevel.AUTO_EXECUTE,
    )
    monitor = ExitMonitorAgent(config, exits, positions, entry_exit_handoff=True)
    candidates = await monitor.scan(quotes)
    assert len(candidates) == 1
    router = OpportunityRouter(
        store=opps,
        notifier=AsyncMock(),
        risk_engine=svc._risk,
        broker=broker,
        brokers={"paper": broker},
        data_bus=quotes,
        execution_service=svc,
        fill_reconciler=worker,
    )
    # Venue quote must reflect the triggered stop for immediate paper execution.
    broker.orders._market_data = quotes
    await opps.save(candidates[0])
    await router._try_execute(candidates[0])
    await worker.reconcile_once()
    assert (
        await paper.get_order_result(accepted.order_id)
    ).status == OrderStatus.CANCELLED
    assert (await positions.get(pid))["status"] == "closed"


async def test_definite_dispatch_nonwrite_releases_admission(
    projection, paper, control
):
    from storage.unit_of_work import PaperWriteNotStarted

    worker, positions, exits, opps = projection
    broker, svc, order, quotes = make_rig(paper, control)
    broker.orders._submit_dispatch = AsyncMock(
        side_effect=PaperWriteNotStarted("database busy before BEGIN")
    )
    result = await svc.submit(broker, "PAPER", order)
    assert result.status == OrderStatus.REJECTED
    assert await control.get("execution:admission:lock") is None


async def test_reset_after_handoff_refuses_registration(projection, paper, control):
    from uuid import uuid4

    (
        worker,
        positions,
        exits,
        opps,
        broker,
        svc,
        order,
        accepted,
        pid,
        close,
    ) = await partial(projection, paper, control)
    await worker.prepare_exit(close, broker, "paper")
    await broker.reset()
    with pytest.raises(ValueError, match="generation"):
        await submit(worker, opps, svc, broker, close)


async def test_reset_after_registration_refuses_dispatch(projection, paper, control):
    from uuid import uuid4

    (
        worker,
        positions,
        exits,
        opps,
        broker,
        svc,
        order,
        accepted,
        pid,
        close,
    ) = await partial(projection, paper, control)
    await worker.prepare_exit(close, broker, "paper")
    await opps.save(close)
    dispatch = await worker.register(close, broker)
    await broker.reset()
    assert (await svc.submit(broker, "PAPER", dispatch)).status == OrderStatus.REJECTED
    assert await control.get("execution:admission:lock") is None


async def test_explicit_smaller_exit_remains_smaller_when_entry_done(
    projection, paper, control
):
    (
        worker,
        positions,
        exits,
        opps,
        broker,
        svc,
        order,
        accepted,
        pid,
        close,
    ) = await partial(projection, paper, control)
    await worker.prepare_exit(close, broker, "paper")
    close.suggested_trade.quantity = D(".1")
    await worker.prepare_exit(close, broker, "paper")
    assert close.suggested_trade.quantity == D(".1")


async def test_shadow_exit_never_cancels_entry(projection, paper, control):
    from agents.router import OpportunityRouter
    from broker.models import Quote
    from types import SimpleNamespace

    (
        worker,
        positions,
        exits,
        opps,
        broker,
        svc,
        order,
        accepted,
        pid,
        close,
    ) = await partial(projection, paper, control)
    await broker.connection.connect()
    quotes = SimpleNamespace(
        get_quote=AsyncMock(
            return_value=Quote(order.symbol, bid=D(90), ask=D(90), last=D(90))
        ),
        get_positions=AsyncMock(
            return_value=await broker.account.get_positions("PAPER")
        ),
        get_balances=AsyncMock(return_value=await broker.account.get_balances("PAPER")),
    )
    router = OpportunityRouter(
        store=opps,
        notifier=AsyncMock(),
        risk_engine=svc._risk,
        broker=broker,
        data_bus=quotes,
        execution_service=svc,
        fill_reconciler=worker,
    )
    router._is_shadow_mode = lambda opp: True
    router._finalize_pre_order_decision = AsyncMock(return_value=True)
    worker.prepare_exit = AsyncMock(wraps=worker.prepare_exit)
    await router._try_execute(close)
    worker.prepare_exit.assert_not_awaited()
    assert (
        await paper.get_order_result(accepted.order_id)
    ).status == OrderStatus.PARTIAL


async def test_entry_completing_before_handoff_resizes_monitor_exit(
    projection, paper, control
):
    (
        worker,
        positions,
        exits,
        opps,
        broker,
        svc,
        order,
        accepted,
        pid,
        close,
    ) = await partial(projection, paper, control)
    close.data["close_full_position"] = True
    await tick(broker, order, order.limit_price, D("5.5"))
    await worker.reconcile_once()
    await worker.prepare_exit(close, broker, "paper")
    assert close.suggested_trade.quantity == 6
