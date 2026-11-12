"""Real Redis + paper SQL ledger commission accounting across partial fills."""

from decimal import Decimal as D
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from broker.models import IBKRFeeModel, FidelityFeeModel, OrderSide, OrderStatus
from execution.service import ExecutionUnavailable
from execution.fill_reconciliation import PaperFillReconciler
from tests.integration.test_dispatch_recovery import paper, control, service
from tests.integration.test_paper_fill_reconciliation import (
    projection,
    opportunity,
    submit,
)
from tests.integration.test_paper_resting_recovery import make_rig, tick

pytestmark = pytest.mark.integration


async def test_minimum_once_replay_restart_and_tracking(projection, paper, control):
    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control, fee_model=IBKRFeeModel())
    accepted = await submit(worker, opps, svc, broker, opportunity(order))
    result, quote = await tick(broker, order, 99, 1, "first")
    assert result[0].commission == D(".35")
    repeated = await broker.orders.process_tick(
        quote, bid_size=D(1), ask_size=D(1), tick_id="first"
    )
    assert repeated == result
    await worker.reconcile_once()
    broker2, svc2, _, _ = make_rig(paper, control, fee_model=IBKRFeeModel())
    await tick(broker2, order, 98, 2)
    await tick(broker2, order, 97, 3)
    await worker.reconcile_once()
    final = await paper.get_order_result(accepted.order_id)
    assert final.commission == D(".35")
    row = (await positions.list_open())[0]
    assert D(row["entry_fees"]) == D(".35")
    balance = await broker2.account.get_balances("PAPER")
    assert balance.cash == D("100000") - D(99) - D(196) - D(291) - D(".35")
    state = await broker2.account.get_risk_state("PAPER")
    assert state.context.daily_pnl == D("-.35")


async def test_cancel_partial_then_new_order_has_new_minimum(paper, control):
    broker, svc, order, _ = make_rig(paper, control, fee_model=IBKRFeeModel())
    first = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, 99, 1)
    await broker.orders.cancel_order(first.order_id)
    second = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, 99, 1)
    assert (await paper.get_order_result(first.order_id)).commission == D(".35")
    assert (await paper.get_order_result(second.order_id)).commission == D(".35")
    assert (await broker.account.get_risk_state("PAPER")).context.daily_pnl == D("-.70")


async def test_amendment_keeps_order_minimum(paper, control):
    broker, svc, order, _ = make_rig(paper, control, fee_model=IBKRFeeModel())
    accepted = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, 99, 1)
    await svc.amend(broker, accepted.order_id, {"quantity": D(3), "limit_price": D(98)})
    await tick(broker, order, 98, 2)
    assert (await paper.get_order_result(accepted.order_id)).commission == D(".35")


async def test_lost_ack_recovery_does_not_recharge_minimum(paper, control):
    broker, svc, order, _ = make_rig(paper, control, fee_model=IBKRFeeModel())
    svc._acknowledge_attempt = AsyncMock(side_effect=TimeoutError("lost"))
    with pytest.raises(ExecutionUnavailable):
        await svc.submit(broker, "PAPER", order)
    attempt = (await svc.reconciliation_status())["attempt"]
    partial, _ = await tick(broker, order, 99, 2)
    await control.set("kill_switch:active", "true")
    await service(broker, control).recover(attempt["token"])
    await tick(broker, order, 98, 4)
    assert (await paper.get_order_result(partial[0].order_id)).commission == D(".35")


async def test_fill_write_failure_rolls_back_minimum_and_retry_charges_once(
    paper, control
):
    broker, svc, order, _ = make_rig(paper, control, fee_model=IBKRFeeModel())
    accepted = await svc.submit(broker, "PAPER", order)
    save = paper.save_order
    paper.save_order = AsyncMock(side_effect=RuntimeError("write failed"))
    with pytest.raises(RuntimeError):
        await tick(broker, order, 99, 2)
    paper.save_order = save
    assert (await paper.get_order_result(accepted.order_id)).commission == 0
    await tick(broker, order, 99, 2)
    await tick(broker, order, 98, 4)
    assert (await paper.get_order_result(accepted.order_id)).commission == D(".35")


async def test_fidelity_sell_minimum_once(paper, control):
    broker, svc, order, _ = make_rig(paper, control, fee_model=FidelityFeeModel())
    order.side, order.limit_price = OrderSide.SELL, D(101)
    accepted = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, 101, D(".1"))
    await tick(broker, order, 102, D(".1"))
    assert (await paper.get_order_result(accepted.order_id)).commission == D(".01")


async def test_partial_fees_top_up_when_quantity_exceeds_minimum(paper, control):
    from risk.rules import MaxPositionSize

    broker, svc, order, _ = make_rig(paper, control, fee_model=IBKRFeeModel())
    svc._risk._rules = [MaxPositionSize(1000000, 1000)]
    order.quantity = D(200)
    accepted = await svc.submit(broker, "PAPER", order)
    await tick(broker, order, 99, 1)
    await tick(broker, order, 98, 199)
    assert (await paper.get_order_result(accepted.order_id)).commission == D(".70")
    assert (await broker.account.get_risk_state("PAPER")).context.daily_pnl == D("-.70")
    assert (await broker.account.get_balances("PAPER")).cash == D("80398.30")


async def test_entry_exit_tracking_and_cash_agree_on_total_commissions(
    projection, paper, control
):
    from broker.models import LimitOrder

    worker, positions, exits, opps = projection
    broker, svc, order, _ = make_rig(paper, control, fee_model=IBKRFeeModel())
    await submit(worker, opps, svc, broker, opportunity(order))
    await tick(broker, order, 99, 1)
    await tick(broker, order, 99, 5)
    await worker.reconcile_once()
    pid = (await positions.list_open())[0]["id"]
    close = LimitOrder(order.symbol, OrderSide.SELL, D(6), "PAPER", limit_price=D(101))
    await submit(worker, opps, svc, broker, opportunity(close, position=pid))
    await tick(broker, close, 101, 1)
    await worker.reconcile_once()
    assert (await positions.get(pid))["status"] == "open"
    await tick(broker, close, 101, 5)
    await worker.reconcile_once()
    row = await positions.get(pid)
    # Sell-side regulatory charge is cumulative too: 6 * .000166 = .0010.
    assert D(row["entry_fees"]) == D(".35")
    assert D(row["exit_fees"]) == D(".3510")
    assert D(row["realized_pnl"]) == D("11.2990")
    assert (await broker.account.get_balances("PAPER")).cash == D("100011.299")
    assert (await broker.account.get_risk_state("PAPER")).context.daily_pnl == D(
        "11.2990"
    )
    assert pid not in await exits._store.load_all()
