"""Tests for ExitMonitorAgent and the router's is_exit bypass."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.models import ActionLevel, AgentConfig, Opportunity, OpportunityStatus
from broker.models import AssetType, MarketOrder, OrderSide, Symbol, Quote
from exits.manager import ExitManager
from exits.rules import StopLoss, TakeProfit, TrailingStop
from strategies.exit_monitor import ExitMonitorAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(name: str = "exit_monitor") -> AgentConfig:
    return AgentConfig(
        name=name,
        strategy="exit_monitor",
        schedule="continuous",
        action_level=ActionLevel.AUTO_EXECUTE,
    )


def _make_position(
    position_id: int = 1,
    symbol: str = "AAPL",
    side: str = "BUY",
    entry_price: str = "100.00",
    entry_quantity: int = 10,
    broker_id: str | None = None,
    account_id: str | None = None,
) -> dict:
    return {
        "id": position_id,
        "agent_name": "test_agent",
        "opportunity_id": f"opp-{position_id}",
        "symbol": symbol,
        "side": side,
        "entry_price": entry_price,
        "entry_quantity": entry_quantity,
        "entry_fees": "0",
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "exit_price": None,
        "exit_fees": None,
        "exit_time": None,
        "exit_reason": None,
        "max_adverse_excursion": "0",
        "status": "open",
        "expires_at": None,
        "broker_id": broker_id,
        "account_id": account_id,
    }


class MockDataBus:
    def __init__(self, quotes: dict[str, Decimal]):
        self._quotes = quotes

    async def get_quote(self, symbol: Symbol) -> Quote | None:
        price = self._quotes.get(symbol.ticker)
        if price is None:
            return None
        return Quote(symbol=symbol, last=price, bid=price, ask=price)


# ---------------------------------------------------------------------------
# ExitMonitorAgent tests
# ---------------------------------------------------------------------------

async def test_triggered_stop_emits_sell_opportunity():
    """Open position with triggered stop → emits SELL opportunity with is_exit=True."""
    position = _make_position(position_id=42, symbol="AAPL", entry_price="100.00", entry_quantity=10)

    exit_manager = ExitManager()
    stop = StopLoss(stop_price=Decimal("95.00"), side="BUY")
    await exit_manager.attach(42, [stop])

    position_store = AsyncMock()
    position_store.list_open = AsyncMock(return_value=[position])

    config = _make_config()
    agent = ExitMonitorAgent(config, exit_manager=exit_manager, position_store=position_store)

    # Current price is 90, below stop of 95 → triggers
    data_bus = MockDataBus({"AAPL": Decimal("90.00")})
    opps = await agent.scan(data_bus)

    assert len(opps) == 1
    opp = opps[0]
    assert opp.is_exit is True
    assert opp.suggested_trade is not None
    assert opp.suggested_trade.side == OrderSide.SELL
    assert opp.suggested_trade.quantity == Decimal("10")
    assert "stop_loss" in opp.reasoning
    assert opp.data["position_id"] == 42
    assert opp.data["tracked_position_id"] == 42


async def test_exit_uses_persisted_account_id():
    position = _make_position(
        position_id=42,
        symbol="AAPL",
        entry_price="100.00",
        entry_quantity=10,
        account_id="acct-123",
    )

    exit_manager = ExitManager()
    await exit_manager.attach(42, [StopLoss(stop_price=Decimal("95.00"), side="BUY")])

    position_store = AsyncMock()
    position_store.list_open = AsyncMock(return_value=[position])

    agent = ExitMonitorAgent(_make_config(), exit_manager=exit_manager, position_store=position_store)
    opps = await agent.scan(MockDataBus({"AAPL": Decimal("90.00")}))

    assert len(opps) == 1
    assert opps[0].suggested_trade.account_id == "acct-123"


async def test_no_trigger_returns_empty():
    """Open position with no triggered rules → no opportunity emitted."""
    position = _make_position(position_id=1, symbol="AAPL", entry_price="100.00", entry_quantity=5)

    exit_manager = ExitManager()
    # Stop is at 80; current price is 110 → not triggered
    stop = StopLoss(stop_price=Decimal("80.00"), side="BUY")
    await exit_manager.attach(1, [stop])

    position_store = AsyncMock()
    position_store.list_open = AsyncMock(return_value=[position])

    config = _make_config()
    agent = ExitMonitorAgent(config, exit_manager=exit_manager, position_store=position_store)

    data_bus = MockDataBus({"AAPL": Decimal("110.00")})
    opps = await agent.scan(data_bus)

    assert opps == []


async def test_multiple_positions_only_triggered_emits():
    """Only positions with triggered rules emit opportunities."""
    pos1 = _make_position(position_id=1, symbol="AAPL", entry_price="100.00", entry_quantity=10)
    pos2 = _make_position(position_id=2, symbol="MSFT", entry_price="200.00", entry_quantity=5)

    exit_manager = ExitManager()
    # AAPL: stop at 95, current price 90 → triggers
    await exit_manager.attach(1, [StopLoss(stop_price=Decimal("95.00"), side="BUY")])
    # MSFT: stop at 180, current price 210 → does not trigger
    await exit_manager.attach(2, [StopLoss(stop_price=Decimal("180.00"), side="BUY")])

    position_store = AsyncMock()
    position_store.list_open = AsyncMock(return_value=[pos1, pos2])

    config = _make_config()
    agent = ExitMonitorAgent(config, exit_manager=exit_manager, position_store=position_store)

    data_bus = MockDataBus({"AAPL": Decimal("90.00"), "MSFT": Decimal("210.00")})
    opps = await agent.scan(data_bus)

    assert len(opps) == 1
    assert opps[0].symbol.ticker == "AAPL"


async def test_missing_exit_manager_returns_empty():
    """Agent without exit_manager warns and returns empty list."""
    position_store = AsyncMock()
    position_store.list_open = AsyncMock(return_value=[_make_position()])

    config = _make_config()
    agent = ExitMonitorAgent(config, exit_manager=None, position_store=position_store)

    data_bus = MockDataBus({"AAPL": Decimal("90.00")})
    opps = await agent.scan(data_bus)

    assert opps == []


async def test_no_open_positions_returns_empty():
    """When there are no open positions, scan returns empty."""
    exit_manager = ExitManager()
    position_store = AsyncMock()
    position_store.list_open = AsyncMock(return_value=[])

    config = _make_config()
    agent = ExitMonitorAgent(config, exit_manager=exit_manager, position_store=position_store)

    data_bus = MockDataBus({})
    opps = await agent.scan(data_bus)

    assert opps == []


async def test_sell_position_emits_buy_opportunity():
    """Exit of a SELL position should produce a BUY suggested trade."""
    position = _make_position(
        position_id=7, symbol="TSLA", side="SELL", entry_price="300.00", entry_quantity=3
    )

    exit_manager = ExitManager()
    # For SELL: stop triggers when price rises above stop_price
    stop = StopLoss(stop_price=Decimal("310.00"), side="SELL")
    await exit_manager.attach(7, [stop])

    position_store = AsyncMock()
    position_store.list_open = AsyncMock(return_value=[position])

    config = _make_config()
    agent = ExitMonitorAgent(config, exit_manager=exit_manager, position_store=position_store)

    data_bus = MockDataBus({"TSLA": Decimal("315.00")})
    opps = await agent.scan(data_bus)

    assert len(opps) == 1
    assert opps[0].suggested_trade.side == OrderSide.BUY
    assert opps[0].is_exit is True


async def test_lowercase_buy_side_is_normalized():
    position = _make_position(position_id=8, symbol="AAPL", side="buy", entry_price="100.00", entry_quantity=2)

    exit_manager = ExitManager()
    await exit_manager.attach(8, [StopLoss(stop_price=Decimal("95.00"), side="BUY")])

    position_store = AsyncMock()
    position_store.list_open = AsyncMock(return_value=[position])

    agent = ExitMonitorAgent(_make_config(), exit_manager=exit_manager, position_store=position_store)
    opps = await agent.scan(MockDataBus({"AAPL": Decimal("90.00")}))

    assert len(opps) == 1
    assert opps[0].suggested_trade.side == OrderSide.SELL


async def test_trailing_stop_updates_and_triggers():
    position = _make_position(position_id=9, symbol="AAPL", side="BUY", entry_price="100.00", entry_quantity=4)

    exit_manager = ExitManager()
    trail = TrailingStop(trail_pct=Decimal("0.05"), side="BUY")
    await exit_manager.attach(9, [trail])

    position_store = AsyncMock()
    position_store.list_open = AsyncMock(return_value=[position])

    agent = ExitMonitorAgent(_make_config(), exit_manager=exit_manager, position_store=position_store)

    first_pass = await agent.scan(MockDataBus({"AAPL": Decimal("110.00")}))
    assert first_pass == []

    second_pass = await agent.scan(MockDataBus({"AAPL": Decimal("104.00")}))
    assert len(second_pass) == 1
    assert second_pass[0].suggested_trade.side == OrderSide.SELL


# ---------------------------------------------------------------------------
# Router: is_exit=True skips sizing engine
# ---------------------------------------------------------------------------

async def test_router_is_exit_skips_sizing_engine():
    """Router should NOT call sizing engine when opportunity.is_exit is True."""
    from agents.router import OpportunityRouter
    from broker.models import (
        AccountBalance, MarketOrder, OrderResult, OrderStatus,
        Quote, Symbol, AssetType, OrderSide,
    )

    store = AsyncMock()
    store.update_status = AsyncMock()
    notifier = AsyncMock()

    symbol = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)
    trade = MarketOrder(
        symbol=symbol,
        side=OrderSide.SELL,
        quantity=Decimal("50"),  # full position quantity — must NOT be resized
        account_id="U123",
    )

    opp = Opportunity(
        id="exit-test-1",
        agent_name="exit_monitor",
        symbol=symbol,
        signal="exit_position",
        confidence=1.0,
        reasoning="stop_loss triggered",
        data={},
        timestamp=datetime.now(timezone.utc),
        suggested_trade=trade,
        is_exit=True,
    )

    broker = MagicMock()
    broker.orders = MagicMock()
    broker.orders.place_order = AsyncMock(
        return_value=OrderResult(
            order_id="ord-99",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("50"),
            avg_fill_price=Decimal("148.00"),
        )
    )

    risk_engine = MagicMock()
    risk_engine.evaluate = AsyncMock(return_value=MagicMock(passed=True, adjusted_quantity=None))

    data_bus = AsyncMock()
    data_bus.get_quote = AsyncMock(
        return_value=Quote(
            symbol=symbol,
            last=Decimal("148.00"),
            bid=Decimal("147.50"),
            ask=Decimal("148.50"),
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

    # Sizing engine that would reduce quantity to 5 — must be bypassed
    sizing_engine = AsyncMock()
    sizing_engine.compute_size = AsyncMock(return_value=Decimal("5"))

    router = OpportunityRouter(
        store=store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        data_bus=data_bus,
        sizing_engine=sizing_engine,
    )

    await router._try_execute(opp)

    # Sizing engine must NOT have been called
    sizing_engine.compute_size.assert_not_called()
    # Full quantity (50) must be preserved on the suggested trade
    assert opp.suggested_trade.quantity == Decimal("50")
    broker.orders.place_order.assert_awaited_once()
