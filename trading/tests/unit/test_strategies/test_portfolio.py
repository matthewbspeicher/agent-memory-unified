import pytest
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from agents.models import AgentConfig, ActionLevel
from broker.models import Position, Symbol
from strategies.portfolio import PositionMonitorAgent, TaxLossHarvestingAgent


class MockDataBus:
    def __init__(self, positions=None, trades=None):
        self._positions = positions or []
        self._trades = trades or []

    async def get_positions(self):
        return self._positions

    async def get_recent_trades(self, limit: int = 100):
        return self._trades


@pytest.mark.asyncio
async def test_position_monitor_agent_stale_and_underwater():
    config = AgentConfig(
        name="monitor",
        strategy="position_monitor",
        schedule="on_demand",
        action_level=ActionLevel.NOTIFY,
        parameters={"stale_days": 30, "underwater_pct": -10.0},
    )
    agent = PositionMonitorAgent(config)

    # Position that is strictly -10% meaning cost=1000, market=900, pnl=-100
    p1 = Position(
        Symbol("AAPL"),
        quantity=Decimal("10"),
        avg_cost=Decimal("100"),
        market_value=Decimal("900"),
        unrealized_pnl=Decimal("-100"),
        realized_pnl=Decimal("0"),
    )

    # Position that is not underwater (pnl > 0)
    p2 = Position(
        Symbol("MSFT"),
        quantity=Decimal("10"),
        avg_cost=Decimal("100"),
        market_value=Decimal("1100"),
        unrealized_pnl=Decimal("100"),
        realized_pnl=Decimal("0"),
    )

    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=40)
    recent_date = now - timedelta(days=10)

    trades = [
        # AAPL traded 40 days ago (stale)
        {
            "order_result": json.dumps({"symbol": {"ticker": "AAPL"}}),
            "created_at": old_date.isoformat(),
        },
        # MSFT traded 10 days ago (not stale)
        {
            "order_result": json.dumps({"symbol": {"ticker": "MSFT"}}),
            "created_at": recent_date.isoformat(),
        },
    ]

    bus = MockDataBus(positions=[p1, p2], trades=trades)
    opps = await agent.scan(bus)

    assert len(opps) == 1
    assert opps[0].symbol.ticker == "AAPL"
    assert "underwater" in opps[0].reasoning
    assert "stale" in opps[0].reasoning
    assert opps[0].data["pnl_pct"] == -10.0


@pytest.mark.asyncio
async def test_tax_loss_harvesting_agent():
    config = AgentConfig(
        name="harvester",
        strategy="tax_loss",
        schedule="on_demand",
        action_level=ActionLevel.SUGGEST_TRADE,
        parameters={"min_loss_amount": 500.0, "wash_sale_days": 30},
    )
    agent = TaxLossHarvestingAgent(config)

    # Position with $600 loss, clear of wash sale (40 days ago)
    p1 = Position(
        Symbol("TSLA"),
        quantity=Decimal("10"),
        avg_cost=Decimal("200"),
        market_value=Decimal("1400"),
        unrealized_pnl=Decimal("-600"),
        realized_pnl=Decimal("0"),
    )

    # Position with $800 loss, but traded 10 days ago (wash sale blocked)
    p2 = Position(
        Symbol("AMZN"),
        quantity=Decimal("10"),
        avg_cost=Decimal("200"),
        market_value=Decimal("1200"),
        unrealized_pnl=Decimal("-800"),
        realized_pnl=Decimal("0"),
    )

    # Position with $200 loss (less than 500 minimum)
    p3 = Position(
        Symbol("GOOGL"),
        quantity=Decimal("10"),
        avg_cost=Decimal("200"),
        market_value=Decimal("1800"),
        unrealized_pnl=Decimal("-200"),
        realized_pnl=Decimal("0"),
    )

    now = datetime.now(timezone.utc)
    trades = [
        {
            "order_result": {"symbol": {"ticker": "TSLA"}},
            "created_at": (now - timedelta(days=40)).isoformat(),
        },
        {
            "order_result": {"symbol": {"ticker": "AMZN"}},
            "created_at": (now - timedelta(days=10)).isoformat(),
        },
        {
            "order_result": {"symbol": {"ticker": "GOOGL"}},
            "created_at": (now - timedelta(days=50)).isoformat(),
        },
    ]

    bus = MockDataBus(positions=[p1, p2, p3], trades=trades)
    opps = await agent.scan(bus)

    assert len(opps) == 1
    assert opps[0].symbol.ticker == "TSLA"
    assert opps[0].data["unrealized_loss"] == 600.0
    assert opps[0].suggested_trade is not None
    assert getattr(opps[0].suggested_trade, "quantity") == Decimal("10")
