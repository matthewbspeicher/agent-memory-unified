"""Application callers must cross real admission, including arbitrage rollback."""

import ast
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.models import Opportunity, OpportunityStatus
from agents.router import OpportunityRouter
from broker.models import AccountBalance, MarketOrder, OrderSide, Quote, Symbol
from execution.arbitrage import ArbCoordinator
from execution.context import AccountRiskState
from execution.models import ArbLeg, ArbState, ArbTrade
from execution.service import ExecutionService
from risk.engine import RiskEngine
from risk.kill_switch import KillSwitch
from risk.rules import MaxDailyLoss, MaxDailyTrades, PortfolioContext
from whatsapp.assistant import WhatsAppAssistant


from tests.execution_controls import AdmissionLuaDouble


class ControlStore(AdmissionLuaDouble):
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


@pytest.fixture(params=["halted", "missing_daily_context"])
def refused_execution(request):
    symbol = Symbol("TEST")
    order = MarketOrder(symbol, OrderSide.BUY, D(2), "paper")
    balance = AccountBalance("paper", D(10000), D(10000), D(10000), D(0))
    state = AccountRiskState(
        PortfolioContext([], balance, daily_pnl=D(0), daily_trade_count=0),
        datetime.now(timezone.utc),
        [],
        "isolated-test-ledger",
    )
    store = ControlStore()
    if request.param == "halted":
        store.data["kill_switch:active"] = "true"
    else:
        state.context.daily_pnl = None
    quote = Quote(symbol, last=D(100))
    broker = SimpleNamespace(
        connection=SimpleNamespace(is_connected=lambda: True),
        account=SimpleNamespace(
            get_risk_state=AsyncMock(side_effect=lambda account: deepcopy(state))
        ),
        market_data=SimpleNamespace(get_quote=AsyncMock(return_value=quote)),
        orders=SimpleNamespace(place_order=AsyncMock(), modify_order=AsyncMock()),
    )
    risk = RiskEngine([MaxDailyLoss(1000), MaxDailyTrades(10)], KillSwitch())
    service = ExecutionService(risk, store)
    service.register_brokers({"test": broker})
    return SimpleNamespace(
        broker=broker,
        order=order,
        state=state,
        risk=risk,
        service=service,
        control=store,
        quote=quote,
        balance=balance,
    )


def arb_setup(rig):
    store = AsyncMock()
    coordinator = ArbCoordinator(
        {"test": rig.broker},
        store,
        SimpleNamespace(order_timeout=1),
        execution_service=rig.service,
    )
    trade = ArbTrade(
        "arb",
        "TEST",
        "TEST",
        ArbLeg("test", rig.order),
        ArbLeg("test", deepcopy(rig.order)),
        10,
    )
    return coordinator, store, trade


async def test_arbitrage_leg_cannot_bypass_real_admission(refused_execution):
    rig = refused_execution
    coordinator, store, trade = arb_setup(rig)
    assert await coordinator._execute_leg(trade, "leg_a") is False
    rig.broker.account.get_risk_state.assert_awaited_once_with("paper")
    rig.broker.orders.place_order.assert_not_awaited()
    store.update_leg_atomic.assert_not_awaited()


async def test_arbitrage_rollback_cannot_bypass_real_admission(refused_execution):
    rig = refused_execution
    coordinator, store, trade = arb_setup(rig)
    trade.leg_a.fill_quantity = D(2)
    trade.leg_a.fill_price = D(100)
    await coordinator._unwind_leg(trade, "leg_a")
    rig.broker.account.get_risk_state.assert_awaited_once_with("paper")
    rig.broker.orders.place_order.assert_not_awaited()
    assert store.update_trade_state.await_args.args[1] == ArbState.FAILED
    assert all(
        call.args[1] != ArbState.UNWOUND
        for call in store.update_trade_state.await_args_list
    )


async def test_whatsapp_confirmation_cannot_bypass_real_admission(refused_execution):
    rig = refused_execution
    client = AsyncMock()
    assistant = WhatsAppAssistant(
        client,
        rig.broker,
        MagicMock(),
        AsyncMock(),
        rig.risk,
        account_id="paper",
        execution_service=rig.service,
    )
    action = SimpleNamespace(
        action_type="place_order",
        data={"symbol": "TEST", "side": "BUY", "quantity": "2"},
    )
    await assistant._execute_confirmed("isolated-test", action)
    rig.broker.account.get_risk_state.assert_awaited_once_with("paper")
    rig.broker.orders.place_order.assert_not_awaited()
    assert client.send_text.await_args.args[1].startswith("Order failed:")


async def test_strategy_router_cannot_bypass_real_admission(refused_execution):
    rig = refused_execution
    data_bus = SimpleNamespace(
        get_quote=AsyncMock(return_value=rig.quote),
        get_positions=AsyncMock(return_value=[]),
        get_balances=AsyncMock(return_value=rig.balance),
    )
    store = AsyncMock()
    store.transition.return_value = True
    router = OpportunityRouter(
        store=store,
        notifier=AsyncMock(),
        risk_engine=rig.risk,
        broker=rig.broker,
        data_bus=data_bus,
        execution_service=rig.service,
    )
    opportunity = Opportunity(
        "refused",
        "test",
        rig.order.symbol,
        "TEST",
        0.9,
        "test",
        {"_opportunity_revision": "unit-saved-revision"},
        datetime.now(timezone.utc),
        suggested_trade=rig.order,
    )
    await router._try_execute(opportunity)
    rig.broker.account.get_risk_state.assert_awaited_once_with("paper")
    rig.broker.orders.place_order.assert_not_awaited()
    store.transition.assert_awaited_with(
        "refused", OpportunityStatus.PENDING, OpportunityStatus.REJECTED,
        revision="unit-saved-revision",
    )
    store.update_status.assert_not_awaited()


def test_raw_order_mutations_are_confined_to_execution_boundary():
    """Adapters implement transport; application modules must call admission."""
    root = Path(__file__).resolve().parents[2]
    violations = []
    checked_service = False
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if relative.parts[0] in {"tests", "adapters", "broker", "scratch"} or any(
            part.startswith(".") for part in relative.parts
        ):
            continue
        if relative.as_posix() == "execution/service.py":
            checked_service = True
            continue
        tree = ast.parse(path.read_text(), filename=str(relative))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr
                in {
                    "place_order",
                    "submit_dispatch",
                    "amend_dispatch",
                    "modify_order",
                    "submit_order",
                    "create_order",
                    "placeOrder",
                }
            ):
                violations.append(f"{relative}:{node.lineno}: {node.func.attr}")
    assert checked_service, "Execution service must exist in the inspected source tree"
    assert violations == [], "Raw application transport bypasses:\n" + "\n".join(
        violations
    )
