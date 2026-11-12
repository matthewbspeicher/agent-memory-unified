"""Execution admission tests use only in-memory providers and mocked transport."""

import asyncio
from contextlib import AsyncExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from broker.models import (
    AccountBalance,
    LimitOrder,
    MarketOrder,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
    Quote,
    Symbol,
)
from execution.context import AccountRiskState, OrderSnapshot
from execution.service import ExecutionService, ExecutionRejected, ExecutionUnavailable
from risk.engine import RiskEngine
from risk.kill_switch import KillSwitch
from risk.rules import (
    PortfolioContext,
    MaxPositionSize,
    MaxDailyLoss,
    MaxDailyTrades,
    MaxOpenPositions,
    RiskResult,
)


from tests.execution_controls import AdmissionLuaDouble


class Store(AdmissionLuaDouble):
    def __init__(self):
        self.data = {"kill_switch:active": "false"}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, nx=False):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def delete(self, key):
        self.data.pop(key, None)


@pytest.fixture
def rig():
    symbol = Symbol("TEST")
    state = AccountRiskState(
        PortfolioContext(
            [],
            AccountBalance("paper", D(10000), D(10000), D(10000), D(0)),
            daily_pnl=D(0),
            daily_trade_count=0,
        ),
        datetime.now(timezone.utc),
        [],
        "test-ledger",
    )
    broker = SimpleNamespace(
        account=SimpleNamespace(
            get_risk_state=AsyncMock(side_effect=lambda account: deepcopy(state))
        ),
        market_data=SimpleNamespace(
            get_quote=AsyncMock(
                return_value=Quote(symbol, last=D(100), ask=D(100), bid=D(99))
            )
        ),
        orders=SimpleNamespace(
            place_order=AsyncMock(
                return_value=OrderResult("one", OrderStatus.SUBMITTED)
            ),
            modify_order=AsyncMock(
                return_value=OrderResult("one", OrderStatus.SUBMITTED)
            ),
            cancel_order=AsyncMock(),
        ),
    )
    store = Store()
    risk = RiskEngine(
        [MaxPositionSize(10000, 10), MaxDailyLoss(1000), MaxDailyTrades(5)],
        KillSwitch(),
    )
    service = ExecutionService(risk, store, timeout_seconds=0.1)
    service.register_brokers({"test": broker})
    order = LimitOrder(symbol, OrderSide.BUY, D(6), "paper", limit_price=D(100))
    return SimpleNamespace(
        service=service, broker=broker, risk=risk, store=store, state=state, order=order
    )


async def test_approved_submit_preserves_caller_order_and_reserves_exposure(rig):
    await rig.service.submit(rig.broker, "paper", rig.order)
    assert rig.order.quantity == 6
    with pytest.raises(ExecutionRejected, match="quantity"):
        await rig.service.submit(rig.broker, "paper", rig.order)
    assert rig.broker.orders.place_order.await_count == 1


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", True])
async def test_bad_quantity_never_reaches_transport(rig, quantity):
    rig.order.quantity = quantity
    with pytest.raises(ExecutionRejected):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


@pytest.mark.parametrize("missing", ["daily_pnl", "daily_trade_count"])
async def test_missing_measured_metrics_blocks(rig, missing):
    setattr(rig.state.context, missing, None)
    with pytest.raises(ExecutionUnavailable):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


async def test_wrong_account_stale_and_wrong_symbol_context(rig):
    with pytest.raises(ExecutionRejected, match="account"):
        await rig.service.submit(rig.broker, "other", rig.order)
    rig.state.observed_at -= timedelta(minutes=1)
    with pytest.raises(ExecutionUnavailable, match="Stale"):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.state.observed_at = datetime.now(timezone.utc)
    rig.broker.market_data.get_quote.return_value = Quote(Symbol("OTHER"), last=D(1))
    with pytest.raises(ExecutionUnavailable, match="symbol"):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


async def test_limit_price_is_included_in_risk_notional(rig):
    rig.order.limit_price = D(2000)
    with pytest.raises(ExecutionRejected, match="dollars"):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


async def test_halt_after_context_collection_still_blocks(rig):
    async def quote(symbol):
        await rig.risk.set_halted(True)
        return Quote(symbol, last=D(100))

    rig.broker.market_data.get_quote.side_effect = quote
    with pytest.raises(ExecutionRejected):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


async def test_halt_after_rules_before_dispatch_still_blocks(rig):
    evaluate = rig.risk.evaluate_order

    async def delayed(*args):
        result = await evaluate(*args)
        await rig.risk.set_halted(True)
        return result

    rig.risk.evaluate_order = delayed
    with pytest.raises(ExecutionUnavailable):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


async def test_concurrent_services_cannot_use_same_capacity(rig):
    second = ExecutionService(rig.risk, rig.store)
    second.register_brokers({"test": rig.broker})
    outcomes = await asyncio.gather(
        rig.service.submit(rig.broker, "paper", rig.order),
        second.submit(rig.broker, "paper", rig.order),
        return_exceptions=True,
    )
    assert sum(isinstance(r, OrderResult) for r in outcomes) == 1
    assert sum(isinstance(r, ExecutionRejected) for r in outcomes) == 1
    assert rig.broker.orders.place_order.await_count == 1


async def test_restart_preserves_pending_reservation(rig):
    await rig.service.submit(rig.broker, "paper", rig.order)
    restarted = ExecutionService(rig.risk, rig.store)
    restarted.register_brokers({"test": rig.broker})
    with pytest.raises(ExecutionRejected):
        await restarted.submit(rig.broker, "paper", rig.order)
    rig.state.terminal_order_ids.add("one")
    await restarted.submit(rig.broker, "paper", rig.order)
    assert rig.broker.orders.place_order.await_count == 2


async def test_unknown_outcome_retains_lock_after_restart(rig):
    rig.broker.orders.place_order.side_effect = TimeoutError("accepted but reply lost")
    with pytest.raises(ExecutionUnavailable, match="reconciliation"):
        await rig.service.submit(rig.broker, "paper", rig.order)
    restarted = ExecutionService(rig.risk, rig.store)
    restarted.register_brokers({"test": rig.broker})
    with pytest.raises(ExecutionUnavailable, match="reconciliation"):
        await restarted.submit(rig.broker, "paper", rig.order)
    assert rig.broker.orders.place_order.await_count == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"totalQuantity": 1000},
        {"account_id": "other"},
        {"symbol": "OTHER"},
        {"limit_price": "NaN"},
        {},
    ],
)
async def test_unsafe_amendments_never_reach_transport(rig, changes):
    await rig.service.submit(rig.broker, "paper", rig.order)
    rig.state.orders = [
        OrderSnapshot("one", deepcopy(rig.order), OrderStatus.SUBMITTED)
    ]
    with pytest.raises(ExecutionRejected):
        await rig.service.amend(rig.broker, "one", changes)
    rig.broker.orders.modify_order.assert_not_awaited()


async def test_amend_reconstructs_full_order_and_rechecks_exposure(rig):
    await rig.service.submit(rig.broker, "paper", rig.order)
    rig.state.orders = [
        OrderSnapshot("one", deepcopy(rig.order), OrderStatus.SUBMITTED)
    ]
    with pytest.raises(ExecutionRejected):
        await rig.service.amend(rig.broker, "one", {"quantity": 11})
    with pytest.raises(ExecutionRejected):
        await rig.service.amend(rig.broker, "one", {"limit_price": 2000})
    await rig.service.amend(rig.broker, "one", {"quantity": 5})
    rig.broker.orders.modify_order.assert_awaited_once_with("one", {"quantity": D(5)})


async def test_partial_fill_amend_counts_only_remaining_exposure(rig):
    await rig.service.submit(rig.broker, "paper", rig.order)
    rig.state.context.positions = [
        Position(rig.order.symbol, D(4), D(100), D(400), D(0), D(0))
    ]
    rig.state.orders = [
        OrderSnapshot("one", deepcopy(rig.order), OrderStatus.PARTIAL, D(4))
    ]
    await rig.service.amend(rig.broker, "one", {"quantity": 10})
    rig.broker.orders.modify_order.assert_awaited_once_with("one", {"quantity": D(10)})


async def test_unknown_amendment_is_rejected(rig):
    with pytest.raises(ExecutionRejected, match="Unknown"):
        await rig.service.amend(rig.broker, "unknown", {"quantity": 1})
    rig.broker.orders.modify_order.assert_not_awaited()


async def test_size_reduction_is_applied_to_actual_transport(rig):
    rig.risk.evaluate_order = AsyncMock(
        return_value=RiskResult(True, adjusted_quantity=D(2))
    )
    await rig.service.submit(rig.broker, "paper", rig.order)
    sent = rig.broker.orders.place_order.call_args.args[1]
    assert sent.quantity == 2
    assert rig.order.quantity == 6


async def test_opposite_pending_order_does_not_manufacture_capacity(rig):
    rig.state.context.positions = [
        Position(rig.order.symbol, D(10), D(100), D(1000), D(0), D(0))
    ]
    sell = deepcopy(rig.order)
    sell.side = OrderSide.SELL
    sell.quantity = D(10)
    rig.state.orders = [OrderSnapshot("sell", sell, OrderStatus.SUBMITTED)]
    with pytest.raises(ExecutionRejected):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


async def test_real_paper_daily_limits_survive_service_restart(tmp_path):
    import aiosqlite
    from storage.paper import PaperStore
    from broker.paper import PaperBroker

    async with (
        aiosqlite.connect(tmp_path / "paper.db") as db,
        AsyncExitStack() as cleanup,
    ):
        db.row_factory = aiosqlite.Row
        ledger = PaperStore(db)
        await ledger.init_tables()
        cleanup.push_async_callback(ledger.close)
        symbol = Symbol("TEST")
        quotes = SimpleNamespace(
            get_quote=AsyncMock(
                return_value=Quote(symbol, last=D(100), ask=D(100), bid=D(100))
            ),
            get_order_book=AsyncMock(return_value={}),
        )
        broker = PaperBroker(ledger, market_data=quotes, max_slippage=0)
        control = Store()
        risk = RiskEngine([MaxDailyLoss(10), MaxDailyTrades(5)], KillSwitch())
        service = ExecutionService(risk, control)
        service.register_brokers({"paper": broker})
        buy = MarketOrder(symbol, OrderSide.BUY, D(2), "PAPER")
        first = await service.submit(broker, "PAPER", buy)
        assert first.status == OrderStatus.FILLED
        # A profitable close avoids the loss guard; counts and journal reconciliation persist.
        quotes.get_quote.return_value = Quote(
            symbol, last=D(110), ask=D(110), bid=D(110)
        )
        second = await service.submit(
            broker, "PAPER", MarketOrder(symbol, OrderSide.SELL, D(2), "PAPER")
        )
        assert second.status == OrderStatus.FILLED
        restarted = ExecutionService(
            RiskEngine([MaxDailyTrades(2)], KillSwitch()), control
        )
        restarted.register_brokers({"paper": broker})
        with pytest.raises(ExecutionRejected, match="Daily trades"):
            await restarted.submit(broker, "PAPER", buy)
        state = await broker.account.get_risk_state("PAPER")
        assert state.context.daily_pnl == 20
        assert state.context.daily_trade_count == 2
        assert state.context.positions == []
        assert len(await ledger.get_order_history("PAPER")) == 2


async def test_real_paper_open_losses_block_new_orders(tmp_path):
    import aiosqlite
    from storage.paper import PaperStore
    from broker.paper import PaperBroker

    async with (
        aiosqlite.connect(tmp_path / "paper.db") as db,
        AsyncExitStack() as cleanup,
    ):
        db.row_factory = aiosqlite.Row
        ledger = PaperStore(db)
        await ledger.init_tables()
        cleanup.push_async_callback(ledger.close)
        symbol = Symbol("TEST")
        quotes = SimpleNamespace(
            get_quote=AsyncMock(
                return_value=Quote(symbol, last=D(100), ask=D(100), bid=D(100))
            ),
            get_order_book=AsyncMock(return_value={}),
        )
        broker = PaperBroker(ledger, market_data=quotes, max_slippage=0)
        service = ExecutionService(
            RiskEngine([MaxDailyLoss(10)], KillSwitch()), Store()
        )
        service.register_brokers({"paper": broker})
        buy = MarketOrder(symbol, OrderSide.BUY, D(2), "PAPER")
        await service.submit(broker, "PAPER", buy)
        quotes.get_quote.return_value = Quote(symbol, last=D(90), ask=D(90), bid=D(90))
        with pytest.raises(ExecutionRejected, match="Daily loss"):
            await service.submit(broker, "PAPER", buy)
        assert len(await ledger.get_order_history("PAPER")) == 1


async def test_optional_rules_cannot_pass_without_required_context(rig):
    from risk.rules import SectorConcentration, MaxCorrelation

    rig.risk.rules.append(SectorConcentration(50))
    with pytest.raises(ExecutionUnavailable, match="sector"):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.risk.rules.pop()
    rig.risk.rules.append(MaxCorrelation(0.8))
    rig.state.context.positions = [
        Position(Symbol("OTHER"), D(1), D(1), D(1), D(0), D(0))
    ]
    with pytest.raises(ExecutionUnavailable, match="histories"):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


async def test_unknown_outcome_has_durable_reconciliation_evidence(rig):
    rig.broker.orders.place_order.side_effect = TimeoutError()
    with pytest.raises(ExecutionUnavailable):
        await rig.service.submit(rig.broker, "paper", rig.order)
    evidence = await rig.service.reconciliation_status()
    assert evidence["attempt"]["token"] == evidence["lock"]
    assert evidence["attempt"]["account"] == "paper"
    assert evidence["attempt"]["broker"] == "test"
    assert evidence["attempt"]["order"]["data"]["quantity"] == "6"
    assert evidence["attempt"]["status"] == "prepared"


async def test_definite_rejection_without_id_does_not_latch_uncertainty(rig):
    rig.broker.orders.place_order.return_value = OrderResult("", OrderStatus.REJECTED)
    result = await rig.service.submit(rig.broker, "paper", rig.order)
    assert result.status == OrderStatus.REJECTED
    assert (await rig.service.reconciliation_status())["lock"] is None


@pytest.mark.parametrize(
    "status,quantity,price",
    [
        (OrderStatus.REJECTED, D(0), None),
        (OrderStatus.SUBMITTED, D(0), None),
        (OrderStatus.PARTIAL, D(3), D(100)),
        (OrderStatus.CANCELLED, D(3), D(100)),
        (OrderStatus.FILLED, D(6), None),
        (OrderStatus.FILLED, D(6), D("NaN")),
        (OrderStatus.FILLED, "6", D(100)),
    ],
)
async def test_receipt_contract_preserves_raw_evidence_and_price_policy(
    rig, status, quantity, price
):
    result = OrderResult(
        "" if status == OrderStatus.REJECTED else "receipt",
        status, quantity, price,
    )
    rig.broker.orders.place_order.return_value = result
    returned = await rig.service.submit(rig.broker, "paper", rig.order)
    assert returned is result
    assert returned.filled_quantity is quantity
    assert returned.avg_fill_price is price
    evidence = await rig.service.reconciliation_status()
    assert evidence["lock"] is None
    assert evidence["attempt"]["status"] == "acknowledged"


@pytest.mark.parametrize(
    "result",
    [
        None,
        OrderResult("", OrderStatus.SUBMITTED),
        OrderResult("bad", "UNKNOWN"),
        OrderResult("bad", OrderStatus.FILLED, D(3)),
        OrderResult("bad", OrderStatus.PARTIAL, D(7)),
        OrderResult("bad", OrderStatus.PARTIAL, D(-1)),
        OrderResult("bad", OrderStatus.PARTIAL, True),
        OrderResult("bad", OrderStatus.PARTIAL, D("NaN")),
    ],
)
async def test_invalid_receipt_remains_uncertain_after_transport(rig, result):
    rig.broker.orders.place_order.return_value = result
    with pytest.raises(ExecutionUnavailable) as raised:
        await rig.service.submit(rig.broker, "paper", rig.order)
    assert raised.value.outcome_unknown is True
    evidence = await rig.service.reconciliation_status()
    assert evidence["lock"] == evidence["attempt"]["dispatch_id"]
    assert evidence["attempt"]["status"] == "prepared"


async def test_blocked_call_does_not_settle_an_earlier_attempt(rig):
    rig.store.data["execution:admission:lock"] = "earlier-attempt"
    with pytest.raises(ExecutionUnavailable) as raised:
        await rig.service.submit(rig.broker, "paper", rig.order)
    assert raised.value.outcome_unknown is False
    assert rig.store.data["execution:admission:lock"] == "earlier-attempt"
    rig.broker.orders.place_order.assert_not_awaited()


async def test_authoritative_reset_epoch_invalidates_old_reservation(rig):
    rig.state.epoch = "before-reset"
    await rig.service.submit(rig.broker, "paper", rig.order)
    rig.state.epoch = "after-reset"
    await rig.service.submit(rig.broker, "paper", rig.order)
    assert rig.broker.orders.place_order.await_count == 2


async def test_paper_symbol_metadata_cannot_evade_position_identity(rig):
    rig.state.symbol_identity = "ticker_asset"
    rig.order.symbol = Symbol("TEST", exchange="NASDAQ")
    with pytest.raises(ExecutionRejected, match="identity"):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


async def test_lost_control_state_and_configured_halt_never_auto_resume(rig):
    rig.store.data.pop("kill_switch:active")
    await rig.risk.initialize_control()
    assert rig.risk.check_kill_active()
    assert rig.store.data["kill_switch:active"] == "true"
    rig.store.data["kill_switch:active"] = "false"
    rig.risk.kill_switch.enable("configured halt")
    await rig.risk.initialize_control()
    assert rig.store.data["kill_switch:active"] == "true"


async def test_empty_policy_is_not_permission_to_submit(rig):
    rig.risk.rules.clear()
    with pytest.raises(ExecutionUnavailable, match="no rules"):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


@pytest.mark.parametrize(
    "case", ["success", "resumed", "changed", "missing", "store_failure"]
)
async def test_terminal_receipt_recovery_is_atomic_and_keeps_halt(rig, case):
    import json

    rig.broker.orders.place_order.return_value = OrderResult(
        "terminal", OrderStatus.FILLED, filled_quantity=D(6)
    )
    # Simulate successful persistence followed by failed admission-lock cleanup.
    rig.store.delete = AsyncMock(side_effect=RuntimeError("lost delete"))
    await rig.service.submit(rig.broker, "paper", rig.order)
    evidence = await rig.service.reconciliation_status()
    token = evidence["lock"]
    rig.state.terminal_order_ids.add("terminal")
    rig.store.data["kill_switch:active"] = "true"

    async def atomic(
        script,
        count,
        lock,
        attempt,
        journal,
        halt,
        expected,
        raw,
        old_journal,
        new_journal,
        recovered,
    ):
        if case == "store_failure":
            raise RuntimeError("Redis unavailable")
        if case == "changed":
            return 0
        assert rig.store.data[lock] == expected
        assert rig.store.data[attempt] == raw
        assert rig.store.data[journal] == old_journal
        assert rig.store.data[halt] == "true"
        rig.store.data[journal] = new_journal
        rig.store.data[attempt] = recovered
        del rig.store.data[lock]
        return 1

    rig.store.eval = AsyncMock(side_effect=atomic)
    if case == "resumed":
        rig.store.data["kill_switch:active"] = "false"
    if case == "missing":
        rig.state.terminal_order_ids.clear()
    if case == "success":
        result = await rig.service.recover_acknowledged(token)
        assert result["status"] == "recovered"
        assert rig.store.data["kill_switch:active"] == "true"
        assert "execution:admission:lock" not in rig.store.data
        assert json.loads(rig.store.data["execution:admission:reservations"]) == []
    else:
        with pytest.raises((ExecutionRejected, RuntimeError)):
            await rig.service.recover_acknowledged(token)
        assert rig.store.data["execution:admission:lock"] == token
    assert rig.broker.orders.place_order.await_count == 1


async def test_prepared_only_attempt_cannot_be_recovered_as_rejected(rig):
    rig.broker.orders.place_order.side_effect = TimeoutError()
    with pytest.raises(ExecutionUnavailable):
        await rig.service.submit(rig.broker, "paper", rig.order)
    token = (await rig.service.reconciliation_status())["lock"]
    rig.store.data["kill_switch:active"] = "true"
    with pytest.raises(ExecutionRejected, match="no durable receipt"):
        await rig.service.recover_acknowledged(token)
    assert (await rig.service.reconciliation_status())["lock"] == token


@pytest.mark.parametrize("holding", ["100", "-100", "0"])
async def test_other_symbol_pending_orders_cannot_free_position_slot(rig, holding):
    other = Symbol("OTHER")
    quantity = D(holding)
    rig.state.context.positions = (
        [Position(other, quantity, D(100), quantity * D(100), D(0), D(0))]
        if quantity
        else []
    )
    sides = (
        [OrderSide.SELL]
        if quantity > 0
        else [OrderSide.BUY]
        if quantity < 0
        else [OrderSide.BUY, OrderSide.SELL]
    )
    rig.state.orders = [
        OrderSnapshot(
            str(index),
            LimitOrder(other, side, D(100), "paper", limit_price=D(100)),
            OrderStatus.SUBMITTED,
        )
        for index, side in enumerate(sides)
    ]
    rig.risk.rules.append(MaxOpenPositions(1))
    with pytest.raises(ExecutionRejected, match="max_open_positions"):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


async def test_portfolio_exposure_values_unacknowledged_other_symbol_and_multiplier(
    rig,
):
    from risk.rules import MaxPortfolioExposure
    from broker.models import AssetType

    rig.risk._rules = [MaxPortfolioExposure(10)]
    rig.broker.market_data.get_quote.side_effect = lambda sym: Quote(
        sym, last=D(100), bid=D(100), ask=D(100)
    )
    # Journal-only orders must reserve money even before provider acknowledgement.
    await rig.service.submit(rig.broker, "paper", rig.order)
    other = deepcopy(rig.order)
    other.symbol = Symbol("OTHER")
    with pytest.raises(ExecutionRejected, match="Cumulative exposure"):
        await rig.service.submit(rig.broker, "paper", other)
    # Derivative multipliers apply exactly once in conservative exposure quotes.
    rig2 = deepcopy(rig.order)
    rig2.symbol = Symbol("OPTION", AssetType.OPTION)
    rig2.quantity = D(1)
    with pytest.raises(ExecutionRejected, match="Cumulative exposure"):
        await rig.service.submit(rig.broker, "paper", rig2)


async def test_exposure_quotes_expiring_during_attempt_write_block_dispatch(
    rig, monkeypatch
):
    from risk.rules import MaxPortfolioExposure
    import execution.service as module

    real_datetime = datetime
    rig.risk._rules = [MaxPortfolioExposure(100)]
    other = deepcopy(rig.order)
    other.symbol = Symbol("OTHER")
    rig.state.orders = [OrderSnapshot("pending", other, OrderStatus.SUBMITTED)]
    rig.broker.market_data.get_quote.side_effect = lambda sym: Quote(
        sym,
        last=D(100),
        timestamp=real_datetime.now(timezone.utc)
        - timedelta(seconds=25 if sym == other.symbol else 0),
    )
    original = rig.service._record_attempt

    written = {"done": False}
    original_fresh = rig.service._fresh

    def fresh(stamp, what):
        if what == "portfolio exposure quote" and written["done"]:
            stamp -= timedelta(seconds=10)
        original_fresh(stamp, what)

    monkeypatch.setattr(rig.service, "_fresh", fresh)

    async def record(*args, **kwargs):
        await original(*args, **kwargs)
        written["done"] = True

    rig.service._record_attempt = record
    with pytest.raises(ExecutionUnavailable, match="portfolio exposure quote"):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()


@pytest.mark.parametrize(
    "multiplier,asset", [(0, "OPTION"), (-1, "FUTURE"), (None, "FUTURE")]
)
async def test_invalid_contract_multiplier_never_dispatches(rig, multiplier, asset):
    from broker.models import AssetType

    rig.order.symbol = Symbol("DERIVATIVE", AssetType(asset), multiplier=multiplier)
    rig.broker.market_data.get_quote.side_effect = lambda sym: Quote(sym, last=D(100))
    with pytest.raises(ExecutionRejected):
        await rig.service.submit(rig.broker, "paper", rig.order)
    rig.broker.orders.place_order.assert_not_awaited()
