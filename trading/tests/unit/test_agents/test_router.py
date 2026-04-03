from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.models import ActionLevel, Opportunity, OpportunityStatus
from agents.router import OpportunityRouter
from broker.models import (
    AccountBalance,
    AssetType,
    MarketOrder,
    OrderResult,
    OrderSide,
    OrderStatus,
    Quote,
    Symbol,
)
from learning.confidence_calibration import ConfidenceCalibrationConfig
from execution.shadow import ShadowDecisionStatus
from learning.strategy_health import StrategyHealthStatus


def _opp() -> Opportunity:
    return Opportunity(
        id="test-1",
        agent_name="test",
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        signal="TEST",
        confidence=0.8,
        reasoning="test",
        data={},
        timestamp=datetime.now(timezone.utc),
    )


def _quote() -> Quote:
    return Quote(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        bid=Decimal("149.50"),
        ask=Decimal("150.50"),
        last=Decimal("150.00"),
        volume=1_000_000,
    )


def _balance() -> AccountBalance:
    return AccountBalance(
        account_id="U123",
        net_liquidation=Decimal("100000"),
        buying_power=Decimal("50000"),
        cash=Decimal("50000"),
        maintenance_margin=Decimal("0"),
    )


class TestOpportunityRouter:
    @pytest.mark.asyncio
    async def test_notify_logs_and_stores(self) -> None:
        store = MagicMock()
        store.save = AsyncMock()
        notifier = MagicMock()
        notifier.send = AsyncMock()

        router = OpportunityRouter(store=store, notifier=notifier)
        await router.route(_opp(), ActionLevel.NOTIFY)

        store.save.assert_awaited_once()
        notifier.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_suggest_trade_stores_as_pending(self) -> None:
        store = MagicMock()
        store.save = AsyncMock()
        notifier = MagicMock()
        notifier.send = AsyncMock()

        router = OpportunityRouter(store=store, notifier=notifier)
        await router.route(_opp(), ActionLevel.SUGGEST_TRADE)

        saved_opp = store.save.call_args[0][0]
        assert saved_opp.status == OpportunityStatus.PENDING

    @pytest.mark.asyncio
    async def test_auto_execute_with_kill_switch(self) -> None:
        store = MagicMock()
        store.save = AsyncMock()
        store.update_status = AsyncMock()
        notifier = MagicMock()
        notifier.send = AsyncMock()
        risk_engine = MagicMock()
        risk_engine.evaluate = AsyncMock(
            return_value=MagicMock(passed=False, reason="kill switch")
        )
        risk_engine.kill_switch = MagicMock(is_enabled=True)
        broker = MagicMock()
        broker.connection.is_connected.return_value = True
        broker.account.get_accounts = AsyncMock(
            return_value=[MagicMock(account_id="U123")]
        )

        data_bus = AsyncMock()
        data_bus.get_quote = AsyncMock(return_value=_quote())
        data_bus.get_positions = AsyncMock(return_value=[])
        data_bus.get_balances = AsyncMock(return_value=_balance())

        router = OpportunityRouter(
            store=store,
            notifier=notifier,
            risk_engine=risk_engine,
            broker=broker,
            data_bus=data_bus,
        )
        opp = _opp()
        opp.suggested_trade = MarketOrder(
            symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id="",
        )
        await router.route(opp, ActionLevel.AUTO_EXECUTE)

        risk_engine.evaluate.assert_awaited_once()
        store.update_status.assert_awaited_with("test-1", OpportunityStatus.REJECTED)


@pytest.mark.asyncio
async def test_try_execute_places_order() -> None:
    """Regression test for the indentation bug that skipped broker order placement."""
    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock(
        return_value=OrderResult(
            order_id="ord-1",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("100"),
            avg_fill_price=Decimal("150.00"),
        )
    )

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(
        return_value=MagicMock(passed=True, adjusted_quantity=None)
    )

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(
        return_value=Quote(
            symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
            bid=Decimal("149.50"),
            ask=Decimal("150.50"),
            last=Decimal("150.00"),
            volume=1_000_000,
        )
    )
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(
        return_value=AccountBalance(
            account_id="U123",
            net_liquidation=Decimal("100000"),
            buying_power=Decimal("50000"),
            cash=Decimal("50000"),
            maintenance_margin=Decimal("0"),
        )
    )

    trade_store = AsyncMock()

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        trade_store=trade_store,
        data_bus=data_bus,
    )

    await router._try_execute(opp)

    broker.orders.place_order.assert_awaited_once_with("U123", trade)
    store.update_status.assert_awaited_with("test-1", OpportunityStatus.EXECUTED)


@pytest.mark.asyncio
async def test_try_execute_records_entry_in_trade_tracker() -> None:
    store = AsyncMock()
    store.update_status = AsyncMock()
    trade_store = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock(
        return_value=OrderResult(
            order_id="ord-1",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("100"),
            avg_fill_price=Decimal("150.00"),
        )
    )

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(
        return_value=MagicMock(passed=True, adjusted_quantity=None)
    )

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(return_value=MagicMock(last=Decimal("150.00")))
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(
        return_value=MagicMock(net_liquidation=Decimal("100000"))
    )

    tracker = AsyncMock()

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        trade_store=trade_store,
        data_bus=data_bus,
        trade_tracker=tracker,
    )

    await router._try_execute(opp)

    tracker.record_entry.assert_called_once()


@pytest.mark.asyncio
async def test_try_execute_allows_zero_placeholder_quantity_when_sizing_engine_supplies_size() -> (
    None
):
    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("0"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock(
        return_value=OrderResult(
            order_id="ord-sized-1",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("7"),
            avg_fill_price=Decimal("150.00"),
        )
    )

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(
        return_value=MagicMock(passed=True, adjusted_quantity=None)
    )

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(return_value=_quote())
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(return_value=_balance())

    sizing_engine = MagicMock()
    sizing_engine.compute_size = AsyncMock(return_value=Decimal("7"))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        data_bus=data_bus,
        sizing_engine=sizing_engine,
    )

    await router._try_execute(opp)

    assert opp.suggested_trade.quantity == Decimal("7")
    sizing_engine.compute_size.assert_awaited_once()
    broker.orders.place_order.assert_awaited_once_with("U123", trade)


@pytest.mark.asyncio
async def test_try_execute_rejects_when_sizing_leaves_zero_quantity() -> None:
    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("0"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock()

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock()

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(return_value=_quote())
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(return_value=_balance())

    sizing_engine = MagicMock()
    sizing_engine.compute_size = AsyncMock(return_value=Decimal("0"))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        data_bus=data_bus,
        sizing_engine=sizing_engine,
    )

    await router._try_execute(opp)

    sizing_engine.compute_size.assert_awaited_once()
    risk_engine.evaluate.assert_not_called()
    broker.orders.place_order.assert_not_awaited()
    store.update_status.assert_awaited_with("test-1", OpportunityStatus.REJECTED)


@pytest.mark.asyncio
async def test_try_execute_attaches_exits_to_tracked_position_id() -> None:
    store = AsyncMock()
    store.update_status = AsyncMock()
    trade_store = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock(
        return_value=OrderResult(
            order_id="ord-1",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("100"),
            avg_fill_price=Decimal("150.00"),
        )
    )

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(
        return_value=MagicMock(passed=True, adjusted_quantity=None)
    )

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(return_value=MagicMock(last=Decimal("150.00")))
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(
        return_value=MagicMock(net_liquidation=Decimal("100000"))
    )

    tracker = AsyncMock()
    tracker.record_entry = AsyncMock(return_value=42)
    exit_manager = MagicMock()
    exit_manager.compute_default_exits.return_value = []
    exit_manager.attach = AsyncMock()

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        trade_store=trade_store,
        data_bus=data_bus,
        trade_tracker=tracker,
        exit_manager=exit_manager,
    )

    await router._try_execute(opp)

    tracker.record_entry.assert_awaited_once()
    exit_manager.attach.assert_awaited_once_with(position_id=42, rules=[])


@pytest.mark.asyncio
async def test_try_execute_exit_records_exit_and_detaches() -> None:
    store = AsyncMock()
    store.update_status = AsyncMock()
    trade_store = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.SELL,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade
    opp.is_exit = True
    opp.data = {"tracked_position_id": 7, "exit_rule": "stop_loss"}

    broker = MagicMock()
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock(
        return_value=OrderResult(
            order_id="ord-exit-1",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("10"),
            avg_fill_price=Decimal("149.00"),
        )
    )

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(
        return_value=MagicMock(passed=True, adjusted_quantity=None)
    )

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(return_value=MagicMock(last=Decimal("149.00")))
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(
        return_value=MagicMock(net_liquidation=Decimal("100000"))
    )

    tracker = AsyncMock()
    exit_manager = MagicMock()
    exit_manager.detach = AsyncMock()

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        trade_store=trade_store,
        data_bus=data_bus,
        trade_tracker=tracker,
        exit_manager=exit_manager,
    )

    await router._try_execute(opp)

    tracker.record_entry.assert_not_called()
    tracker.record_exit.assert_awaited_once()
    args = tracker.record_exit.await_args.args
    assert args[0] == 7
    assert args[2] == "stop_loss"
    exit_manager.detach.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_try_execute_rejects_when_confidence_calibration_rejects() -> None:
    store = AsyncMock()
    store.update_status = AsyncMock()
    store.update_data = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock()

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(
        return_value=MagicMock(passed=True, adjusted_quantity=None)
    )

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(
        return_value=Quote(
            symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
            bid=Decimal("149.50"),
            ask=Decimal("150.50"),
            last=Decimal("150.00"),
            volume=1_000_000,
        )
    )
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(
        return_value=AccountBalance(
            account_id="U123",
            net_liquidation=Decimal("100000"),
            buying_power=Decimal("50000"),
            cash=Decimal("50000"),
            maintenance_margin=Decimal("0"),
        )
    )

    calibration_store = MagicMock()
    calibration_store.get = AsyncMock(
        return_value={
            "trade_count": 60,
            "avg_net_return_pct": -0.02,
            "avg_net_pnl": "-25.00",
        }
    )

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        data_bus=data_bus,
        confidence_calibration_store=calibration_store,
        confidence_calibration_config=ConfidenceCalibrationConfig(allow_reject=True),
    )

    await router._try_execute(opp)

    broker.orders.place_order.assert_not_awaited()
    store.update_status.assert_awaited_with("test-1", OpportunityStatus.REJECTED)
    calibration_store.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_try_execute_scales_quantity_from_confidence_calibration() -> None:
    store = AsyncMock()
    store.update_status = AsyncMock()
    store.update_data = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock(
        return_value=OrderResult(
            order_id="ord-cal-1",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("5"),
            avg_fill_price=Decimal("150.00"),
        )
    )

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(
        return_value=MagicMock(passed=True, adjusted_quantity=None)
    )

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(
        return_value=Quote(
            symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
            bid=Decimal("149.50"),
            ask=Decimal("150.50"),
            last=Decimal("150.00"),
            volume=1_000_000,
        )
    )
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(
        return_value=AccountBalance(
            account_id="U123",
            net_liquidation=Decimal("100000"),
            buying_power=Decimal("50000"),
            cash=Decimal("50000"),
            maintenance_margin=Decimal("0"),
        )
    )

    calibration_store = MagicMock()
    calibration_store.get = AsyncMock(
        return_value={
            "trade_count": 30,
            "avg_net_return_pct": 0.003,
            "avg_net_pnl": "20.00",
        }
    )

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        data_bus=data_bus,
        confidence_calibration_store=calibration_store,
        confidence_calibration_config=ConfidenceCalibrationConfig(),
    )

    await router._try_execute(opp)

    assert opp.suggested_trade.quantity == Decimal("5")
    broker.orders.place_order.assert_awaited_once_with("U123", trade)


@pytest.mark.asyncio
async def test_route_shadow_auto_execute_records_allowed_shadow_instead_of_order() -> (
    None
):
    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock()

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(
        return_value=MagicMock(passed=True, adjusted_quantity=None)
    )

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(
        return_value=Quote(
            symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
            bid=Decimal("149.50"),
            ask=Decimal("150.50"),
            last=Decimal("150.00"),
            volume=1_000_000,
        )
    )
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(
        return_value=AccountBalance(
            account_id="U123",
            net_liquidation=Decimal("100000"),
            buying_power=Decimal("50000"),
            cash=Decimal("50000"),
            maintenance_margin=Decimal("0"),
        )
    )

    sizing_engine = MagicMock()
    sizing_engine.compute_size = AsyncMock(return_value=Decimal("7"))

    health_engine = MagicMock()
    health_engine.get_status = AsyncMock(return_value=MagicMock(value="healthy"))

    calibration_store = MagicMock()
    calibration_store.get = AsyncMock(return_value=None)

    shadow_executor = MagicMock()
    shadow_executor.record = AsyncMock(return_value={"id": "shadow-1"})

    runner = MagicMock()
    runner.get_agent.return_value = MagicMock(config=MagicMock(shadow_mode=True))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        data_bus=data_bus,
        sizing_engine=sizing_engine,
        health_engine=health_engine,
        confidence_calibration_store=calibration_store,
        confidence_calibration_config=ConfidenceCalibrationConfig(),
        shadow_executor=shadow_executor,
        runner=runner,
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    data_bus.get_quote.assert_awaited()
    sizing_engine.compute_size.assert_awaited_once()
    health_engine.get_status.assert_any_await("test")
    calibration_store.get.assert_awaited_once()
    risk_engine.evaluate.assert_awaited_once()
    shadow_executor.record.assert_awaited_once()
    assert (
        shadow_executor.record.await_args.kwargs["decision_status"]
        == ShadowDecisionStatus.ALLOWED
    )
    broker.orders.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_shadow_auto_execute_records_blocked_shadow_when_risk_fails() -> (
    None
):
    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock()

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(
        return_value=MagicMock(
            passed=False, reason="risk limit", adjusted_quantity=None
        )
    )

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(
        return_value=Quote(
            symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
            bid=Decimal("149.50"),
            ask=Decimal("150.50"),
            last=Decimal("150.00"),
            volume=1_000_000,
        )
    )
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(
        return_value=AccountBalance(
            account_id="U123",
            net_liquidation=Decimal("100000"),
            buying_power=Decimal("50000"),
            cash=Decimal("50000"),
            maintenance_margin=Decimal("0"),
        )
    )

    shadow_executor = MagicMock()
    shadow_executor.record = AsyncMock(return_value={"id": "shadow-2"})

    runner = MagicMock()
    runner.get_agent.return_value = MagicMock(config=MagicMock(shadow_mode=True))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        data_bus=data_bus,
        shadow_executor=shadow_executor,
        runner=runner,
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    risk_engine.evaluate.assert_awaited_once()
    shadow_executor.record.assert_awaited_once()
    assert (
        shadow_executor.record.await_args.kwargs["decision_status"]
        == ShadowDecisionStatus.BLOCKED_RISK
    )
    broker.orders.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_shadow_auto_execute_records_blocked_shadow_when_health_fails() -> (
    None
):
    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock()

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock()

    health_engine = MagicMock()
    health_engine.get_status = AsyncMock(return_value=StrategyHealthStatus.SHADOW_ONLY)

    shadow_executor = MagicMock()
    shadow_executor.record = AsyncMock(return_value={"id": "shadow-health"})

    runner = MagicMock()
    runner.get_agent.return_value = MagicMock(config=MagicMock(shadow_mode=True))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        health_engine=health_engine,
        shadow_executor=shadow_executor,
        runner=runner,
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    shadow_executor.record.assert_awaited_once()
    assert (
        shadow_executor.record.await_args.kwargs["decision_status"]
        == ShadowDecisionStatus.BLOCKED_HEALTH
    )
    risk_engine.evaluate.assert_not_called()
    broker.orders.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_shadow_auto_execute_records_blocked_shadow_when_health_fails_with_shadow_mode_false() -> (
    None
):
    """Agent with shadow_mode=False but health SHADOW_ONLY should still record shadow decision."""
    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock()

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock()

    health_engine = MagicMock()
    health_engine.get_status = AsyncMock(return_value=StrategyHealthStatus.SHADOW_ONLY)

    shadow_executor = MagicMock()
    shadow_executor.record = AsyncMock(return_value={"id": "shadow-health"})

    runner = MagicMock()
    runner.get_agent.return_value = MagicMock(config=MagicMock(shadow_mode=False))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        health_engine=health_engine,
        shadow_executor=shadow_executor,
        runner=runner,
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    shadow_executor.record.assert_awaited_once()
    assert (
        shadow_executor.record.await_args.kwargs["decision_status"]
        == ShadowDecisionStatus.BLOCKED_HEALTH
    )
    risk_engine.evaluate.assert_not_called()
    broker.orders.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_router_triggers_shadow_for_registry_shadow_mode() -> None:
    """Agent with shadow_mode=True in config runs shadow path."""
    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock()

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(
        return_value=MagicMock(passed=True, adjusted_quantity=None)
    )

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(return_value=_quote())
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(return_value=_balance())

    health_engine = MagicMock()
    health_engine.get_status = AsyncMock(return_value=StrategyHealthStatus.NORMAL)

    shadow_executor = MagicMock()
    shadow_executor.record = AsyncMock(return_value={"id": "shadow-registry"})

    runner = MagicMock()
    runner.get_agent.return_value = MagicMock(config=MagicMock(shadow_mode=True))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        data_bus=data_bus,
        health_engine=health_engine,
        shadow_executor=shadow_executor,
        runner=runner,
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    # Should NOT place order (shadow mode)
    broker.orders.place_order.assert_not_awaited()
    # Should create shadow record
    shadow_executor.record.assert_awaited_once()
    assert (
        shadow_executor.record.await_args.kwargs["decision_status"]
        == ShadowDecisionStatus.ALLOWED
    )


@pytest.mark.asyncio
async def test_route_shadow_regime_block_records_shadow_decision() -> None:
    store = AsyncMock()
    store.save = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    opp = _opp()
    opp.suggested_trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp.data = {"regime": {"trend": "bear"}}

    runner = MagicMock()
    runner.get_agent.return_value = MagicMock(
        config=MagicMock(
            shadow_mode=True,
            regime_policy_mode="static_gate",
            allowed_regimes={"trend": ["bull"]},
            disallowed_regimes={},
        )
    )

    shadow_executor = MagicMock()
    shadow_executor.record = AsyncMock(return_value={"id": "shadow-regime"})

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        shadow_executor=shadow_executor,
        runner=runner,
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    shadow_executor.record.assert_awaited_once()
    assert (
        shadow_executor.record.await_args.kwargs["decision_status"]
        == ShadowDecisionStatus.BLOCKED_REGIME
    )
    store.update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_shadow_auto_execute_records_blocked_shadow_when_calibration_rejects() -> (
    None
):
    store = AsyncMock()
    store.update_status = AsyncMock()
    store.update_data = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock()

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock()

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(return_value=_quote())
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(return_value=_balance())

    calibration_store = MagicMock()
    calibration_store.get = AsyncMock(
        return_value={
            "trade_count": 60,
            "avg_net_return_pct": -0.02,
            "avg_net_pnl": "-25.00",
        }
    )

    shadow_executor = MagicMock()
    shadow_executor.record = AsyncMock(return_value={"id": "shadow-cal"})

    runner = MagicMock()
    runner.get_agent.return_value = MagicMock(config=MagicMock(shadow_mode=True))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        data_bus=data_bus,
        confidence_calibration_store=calibration_store,
        confidence_calibration_config=ConfidenceCalibrationConfig(allow_reject=True),
        shadow_executor=shadow_executor,
        runner=runner,
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    calibration_store.get.assert_awaited_once()
    shadow_executor.record.assert_awaited_once()
    assert (
        shadow_executor.record.await_args.kwargs["decision_status"]
        == ShadowDecisionStatus.BLOCKED_CALIBRATION
    )
    risk_engine.evaluate.assert_not_called()
    broker.orders.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_shadow_auto_execute_records_blocked_shadow_when_throttle_zeroes_quantity() -> (
    None
):
    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock()

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock()

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(return_value=_quote())
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(return_value=_balance())

    health_engine = MagicMock()
    health_engine.get_status = AsyncMock(return_value=StrategyHealthStatus.THROTTLED)
    health_engine.get_throttle_multiplier = AsyncMock(return_value=0.0)

    shadow_executor = MagicMock()
    shadow_executor.record = AsyncMock(return_value={"id": "shadow-throttle"})

    runner = MagicMock()
    runner.get_agent.return_value = MagicMock(config=MagicMock(shadow_mode=True))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        data_bus=data_bus,
        health_engine=health_engine,
        shadow_executor=shadow_executor,
        runner=runner,
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    shadow_executor.record.assert_awaited_once()
    assert (
        shadow_executor.record.await_args.kwargs["decision_status"]
        == ShadowDecisionStatus.BLOCKED_HEALTH
    )
    risk_engine.evaluate.assert_not_called()
    broker.orders.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_shadow_auto_execute_records_blocked_shadow_for_invalid_initial_quantity() -> (
    None
):
    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("0"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock()

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock()

    shadow_executor = MagicMock()
    shadow_executor.record = AsyncMock(return_value={"id": "shadow-invalid"})

    runner = MagicMock()
    runner.get_agent.return_value = MagicMock(config=MagicMock(shadow_mode=True))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        shadow_executor=shadow_executor,
        runner=runner,
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    shadow_executor.record.assert_awaited_once()
    assert (
        shadow_executor.record.await_args.kwargs["decision_status"]
        == ShadowDecisionStatus.BLOCKED_INVALID_QUANTITY
    )
    risk_engine.evaluate.assert_not_called()
    broker.orders.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_shadow_auto_execute_records_blocked_shadow_for_post_risk_zero_quantity() -> (
    None
):
    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    trade = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        account_id="U123",
    )
    opp = _opp()
    opp.suggested_trade = trade

    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock()

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(
        return_value=MagicMock(passed=True, adjusted_quantity=Decimal("0"))
    )

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(return_value=_quote())
    data_bus.get_positions = AsyncMock(return_value=[])
    data_bus.get_balances = AsyncMock(return_value=_balance())

    shadow_executor = MagicMock()
    shadow_executor.record = AsyncMock(return_value={"id": "shadow-post-risk-zero"})

    runner = MagicMock()
    runner.get_agent.return_value = MagicMock(config=MagicMock(shadow_mode=True))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        data_bus=data_bus,
        shadow_executor=shadow_executor,
        runner=runner,
    )

    await router.route(opp, ActionLevel.AUTO_EXECUTE)

    shadow_executor.record.assert_awaited_once()
    assert (
        shadow_executor.record.await_args.kwargs["decision_status"]
        == ShadowDecisionStatus.BLOCKED_INVALID_QUANTITY
    )
    broker.orders.place_order.assert_not_awaited()
