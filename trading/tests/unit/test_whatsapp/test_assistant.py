import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from whatsapp.assistant import WhatsAppAssistant
from broker.models import Position, Symbol, AssetType, AccountBalance


def _execution_service():
    """Inject the admission seam while preserving assistant transport assertions."""

    async def submit(broker, account_id, order):
        return await broker.orders.place_order(account_id, order)

    service = MagicMock()
    service.submit = AsyncMock(side_effect=submit)
    return service


@pytest.fixture
def deps():
    client = AsyncMock()
    # record_inbound is sync in real WhatsAppClient — use MagicMock so the
    # returned coroutine isn't dropped unawaited (produces RuntimeWarning).
    client.record_inbound = MagicMock()
    broker = MagicMock()
    broker.account.get_positions = AsyncMock(
        return_value=[
            Position(
                symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
                quantity=Decimal("100"),
                avg_cost=Decimal("150"),
                market_value=Decimal("15200"),
                unrealized_pnl=Decimal("200"),
                realized_pnl=Decimal("0"),
            )
        ]
    )
    broker.account.get_balances = AsyncMock(
        return_value=AccountBalance(
            account_id="U123",
            net_liquidation=Decimal("100000"),
            cash=Decimal("50000"),
            buying_power=Decimal("50000"),
            maintenance_margin=Decimal("0"),
        )
    )
    runner = MagicMock()
    runner.list_agents = MagicMock(return_value=[])
    opp_store = AsyncMock()
    opp_store.list = AsyncMock(return_value=[])
    risk_engine = MagicMock()
    risk_engine.set_halted = AsyncMock(return_value=[])

    return client, broker, runner, opp_store, risk_engine


@pytest.fixture
def assistant(deps):
    client, broker, runner, opp_store, risk_engine = deps
    return WhatsAppAssistant(
        client=client,
        broker=broker,
        runner=runner,
        opp_store=opp_store,
        risk_engine=risk_engine,
        account_id="U123",
        execution_service=_execution_service(),
    )


@pytest.fixture
def external_store():
    store = AsyncMock()
    store.get_balances = AsyncMock(
        return_value=[
            {
                "account_id": "X12345",
                "account_name": "INDIVIDUAL",
                "net_liquidation": "50000.00",
                "cash": "5000.00",
                "broker": "fidelity",
            }
        ]
    )
    store.get_positions = AsyncMock(
        return_value=[
            {
                "account_id": "X12345",
                "symbol": "MSFT",
                "description": "Microsoft Corp",
                "quantity": "50",
                "last_price": "400.00",
                "current_value": "20000.00",
                "cost_basis": "18000.00",
            }
        ]
    )
    store.get_import_age = AsyncMock(return_value=2.5)
    return store


@pytest.fixture
def assistant_with_external(deps, external_store):
    client, broker, runner, opp_store, risk_engine = deps
    return WhatsAppAssistant(
        client=client,
        broker=broker,
        runner=runner,
        opp_store=opp_store,
        risk_engine=risk_engine,
        account_id="U123",
        execution_service=_execution_service(),
        external_store=external_store,
    )


@pytest.mark.asyncio
async def test_portfolio_command(assistant, deps):
    client = deps[0]
    await assistant.handle("15551234567", "/portfolio", "msg-1")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "Portfolio Total" in msg
    assert "IBKR" in msg


@pytest.mark.asyncio
async def test_portfolio_summary_with_external(
    assistant_with_external, deps, external_store
):
    client = deps[0]
    await assistant_with_external.handle("15551234567", "/portfolio", "msg-1")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "Portfolio Total" in msg
    assert "IBKR" in msg
    assert "Fidelity" in msg
    assert "INDIVIDUAL" in msg
    # Total should be 100000 + 50000 = 150000
    assert "150,000" in msg


@pytest.mark.asyncio
async def test_portfolio_detailed(assistant_with_external, deps, external_store):
    client = deps[0]
    await assistant_with_external.handle("15551234567", "/portfolio detailed", "msg-1")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "AAPL" in msg  # IBKR position
    assert "MSFT" in msg  # Fidelity position
    assert "Fidelity (INDIVIDUAL)" in msg


@pytest.mark.asyncio
async def test_portfolio_fidelity_only(assistant_with_external, deps, external_store):
    client = deps[0]
    await assistant_with_external.handle("15551234567", "/portfolio fidelity", "msg-1")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "MSFT" in msg
    assert "IBKR" not in msg


@pytest.mark.asyncio
async def test_portfolio_fidelity_no_store(assistant, deps):
    client = deps[0]
    await assistant.handle("15551234567", "/portfolio fidelity", "msg-1")
    msg = client.send_text.call_args[0][1]
    assert "No external portfolio data" in msg


@pytest.mark.asyncio
async def test_portfolio_staleness_warning(deps):
    client, broker, runner, opp_store, risk_engine = deps
    store = AsyncMock()
    store.get_balances = AsyncMock(return_value=[])
    store.get_positions = AsyncMock(return_value=[])
    store.get_import_age = AsyncMock(return_value=30.0)  # 30 hours old
    a = WhatsAppAssistant(
        client=client,
        broker=broker,
        runner=runner,
        opp_store=opp_store,
        risk_engine=risk_engine,
        account_id="U123",
        execution_service=_execution_service(),
        external_store=store,
    )
    await a.handle("15551234567", "/portfolio", "msg-1")
    msg = client.send_text.call_args[0][1]
    assert "Warning" in msg
    assert "30 hours ago" in msg


@pytest.mark.asyncio
async def test_help_command(assistant, deps):
    client = deps[0]
    await assistant.handle("15551234567", "/help", "msg-2")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "/portfolio" in msg


@pytest.mark.asyncio
async def test_buy_command_creates_confirmation(assistant, deps):
    client = deps[0]
    await assistant.handle("15551234567", "/buy AAPL 100", "msg-3")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "AAPL" in msg
    assert assistant._confirmation.has_pending("15551234567")


@pytest.mark.asyncio
async def test_approve_command(assistant, deps):
    deps[0]
    opp_store = deps[3]
    opp_store.get = AsyncMock(return_value={"id": "opp-1", "status": "pending"})
    await assistant.handle("15551234567", "/approve opp-1", "msg-4")
    opp_store.update_status.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_text_falls_back_to_no_llm_message(assistant, deps):
    """Without anthropic_api_key, freeform text should get a fallback message."""
    client = deps[0]
    await assistant.handle("15551234567", "how's my portfolio doing?", "msg-5")
    client.send_text.assert_called()
    msg = client.send_text.call_args[0][1]
    assert "/help" in msg.lower() or "command" in msg.lower()


@pytest.mark.asyncio
async def test_confirmed_order_uses_execution_boundary(assistant, deps):
    from types import SimpleNamespace
    from broker.models import OrderResult, OrderStatus

    broker = deps[1]
    broker.orders.place_order = AsyncMock(
        return_value=OrderResult(
            "checked", OrderStatus.FILLED, Decimal("2"), Decimal("100")
        )
    )
    action = SimpleNamespace(
        action_type="place_order",
        data={"symbol": "AAPL", "side": "BUY", "quantity": "2"},
    )
    await assistant._execute_confirmed("15551234567", action)
    assistant._execution.submit.assert_awaited_once()
    called_broker, account_id, order = assistant._execution.submit.await_args.args
    assert called_broker is broker
    assert account_id == "U123"
    assert order.quantity == Decimal("2")
    broker.orders.place_order.assert_awaited_once_with(account_id, order)


@pytest.mark.asyncio
async def test_boundary_rejection_does_not_place_whatsapp_order(assistant, deps):
    from types import SimpleNamespace

    broker = deps[1]
    broker.orders.place_order = AsyncMock()
    assistant._execution.submit.side_effect = RuntimeError("Risk denied")
    action = SimpleNamespace(
        action_type="place_order",
        data={"symbol": "AAPL", "side": "BUY", "quantity": "2"},
    )
    await assistant._execute_confirmed("15551234567", action)
    broker.orders.place_order.assert_not_awaited()
    assert "Order failed: Risk denied" in deps[0].send_text.await_args.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_confirmed_halt_toggle_uses_persisted_control(assistant, deps, enabled):
    from types import SimpleNamespace

    await assistant._execute_confirmed(
        "15551234567",
        SimpleNamespace(action_type="toggle_kill", data={"enable": enabled}),
    )
    deps[4].set_halted.assert_awaited_once_with(
        enabled, "Enabled via WhatsApp" if enabled else "Resumed via WhatsApp"
    )
    deps[4].kill_switch.enable.assert_not_called()
    deps[4].kill_switch.disable.assert_not_called()


def _reply_token(client):
    import re

    return re.search(r"Reply \*([^*]+)\*", client.send_text.await_args.args[1]).group(1)


@pytest.mark.asyncio
async def test_handle_confirmation_consumes_token_before_concurrent_execution(
    assistant, deps
):
    import asyncio
    from broker.models import OrderResult, OrderStatus

    broker = deps[1]
    broker.orders.place_order = AsyncMock(
        return_value=OrderResult("accepted", OrderStatus.SUBMITTED)
    )
    await assistant.handle("phone-a", "/buy AAPL 2", "create")
    token = _reply_token(deps[0])
    assistant._execution.submit.assert_not_awaited()
    await asyncio.gather(
        assistant.handle("phone-a", token, "confirm-1"),
        assistant.handle("phone-a", token, "confirm-duplicate"),
    )
    assistant._execution.submit.assert_awaited_once()
    broker.orders.place_order.assert_awaited_once()
    assert not assistant._confirmation.has_pending("phone-a")


@pytest.mark.asyncio
async def test_handle_confirmation_is_phone_scoped(assistant, deps):
    from broker.models import OrderResult, OrderStatus

    deps[1].orders.place_order = AsyncMock(
        return_value=OrderResult("accepted", OrderStatus.SUBMITTED)
    )
    await assistant.handle("phone-a", "/buy AAPL 2", "create")
    token = _reply_token(deps[0])
    await assistant.handle("phone-b", token, "wrong-phone")
    assistant._execution.submit.assert_not_awaited()
    assert assistant._confirmation.has_pending("phone-a")
    await assistant.handle("phone-a", token, "correct-phone")
    assistant._execution.submit.assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_handle_confirmation_never_reaches_boundary(
    assistant, deps, monkeypatch
):
    import time

    await assistant.handle("phone-a", "/buy AAPL 2", "create")
    token = _reply_token(deps[0])
    expired_time = time.time() + 301
    monkeypatch.setattr("whatsapp.confirmation.time.time", lambda: expired_time)
    await assistant.handle("phone-a", token, "expired")
    assistant._execution.submit.assert_not_awaited()
    assert not assistant._confirmation.has_pending("phone-a")


@pytest.mark.asyncio
async def test_cancelled_handle_confirmation_cannot_be_replayed(assistant, deps):
    await assistant.handle("phone-a", "/buy AAPL 2", "create")
    token = _reply_token(deps[0])
    await assistant.handle("phone-a", "CANCEL", "cancel")
    await assistant.handle("phone-a", token, "replay")
    assistant._execution.submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_token_reaches_real_boundary_and_halt_blocks_transport(
    assistant, deps
):
    from datetime import datetime, timezone
    from broker.models import Quote
    from execution.context import AccountRiskState
    from execution.service import ExecutionService
    from risk.engine import RiskEngine
    from risk.kill_switch import KillSwitch
    from risk.rules import MaxDailyLoss, PortfolioContext

    class ControlStore:
        def __init__(self):
            self.data = {"kill_switch:active": "true"}

        async def get(self, key):
            return self.data.get(key)

        async def set(self, key, value, nx=False):
            if nx and key in self.data:
                return False
            self.data[key] = value
            return True

        async def delete(self, key):
            self.data.pop(key, None)

    broker = deps[1]
    state = AccountRiskState(
        PortfolioContext(
            [],
            await broker.account.get_balances("U123"),
            daily_pnl=Decimal("0"),
            daily_trade_count=0,
        ),
        datetime.now(timezone.utc),
        [],
        "isolated-test-ledger",
    )
    broker.account.get_risk_state = AsyncMock(return_value=state)
    broker.market_data.get_quote = AsyncMock(
        return_value=Quote(Symbol("AAPL"), last=Decimal("100"))
    )
    broker.orders.place_order = AsyncMock()
    engine = RiskEngine([MaxDailyLoss(1000)], KillSwitch())
    service = ExecutionService(engine, ControlStore())
    service.register_brokers({"test": broker})
    assistant._execution = service
    assistant._risk_engine = engine
    await assistant.handle("phone-a", "/buy AAPL 2", "create")
    token = _reply_token(deps[0])
    await assistant.handle("phone-a", token, "confirm")
    broker.account.get_risk_state.assert_awaited_once_with("U123")
    broker.orders.place_order.assert_not_awaited()
    assert "Order failed:" in deps[0].send_text.await_args.args[1]
    assert "Kill switch" in deps[0].send_text.await_args.args[1]
    assert not assistant._confirmation.has_pending("phone-a")


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/kill", "/unkill"])
async def test_handle_control_persistence_failure_never_reports_success(
    assistant, deps, command
):
    deps[4].set_halted.side_effect = ConnectionError("control unavailable")
    await assistant.handle("phone-a", command, "create")
    token = _reply_token(deps[0])
    deps[0].send_text.reset_mock()
    await assistant.handle("phone-a", token, "confirm")
    deps[4].set_halted.assert_awaited_once()
    assert deps[0].send_text.await_count == 1
    message = deps[0].send_text.await_args.args[1]
    assert "update failed" in message
    assert "ENABLED" not in message and "DISABLED" not in message
