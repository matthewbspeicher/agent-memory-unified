from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal

from agents.models import AgentConfig, ActionLevel
from broker.models import OrderSide


async def test_rsi_oversold_includes_buy_trade():
    from strategies.rsi import RSIAgent

    config = AgentConfig(
        name="test_rsi",
        strategy="rsi",
        schedule="cron",
        action_level=ActionLevel.AUTO_EXECUTE,
        parameters={"oversold": 30, "overbought": 70, "period": 14},
    )
    agent = RSIAgent(config)

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[MagicMock(ticker="AAPL")])
    data.get_rsi = AsyncMock(return_value=25.0)

    opps = await agent.scan(data)
    assert len(opps) == 1
    assert opps[0].signal == "RSI_OVERSOLD"
    assert opps[0].suggested_trade is not None
    assert opps[0].suggested_trade.side == OrderSide.BUY
    assert opps[0].suggested_trade.quantity == Decimal("1")


async def test_rsi_overbought_no_trade():
    """RSI_OVERBOUGHT should NOT auto-execute in Phase 1."""
    from strategies.rsi import RSIAgent

    config = AgentConfig(
        name="test_rsi",
        strategy="rsi",
        schedule="cron",
        action_level=ActionLevel.AUTO_EXECUTE,
        parameters={"oversold": 30, "overbought": 70, "period": 14},
    )
    agent = RSIAgent(config)

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[MagicMock(ticker="AAPL")])
    data.get_rsi = AsyncMock(return_value=75.0)

    opps = await agent.scan(data)
    assert len(opps) == 1
    assert opps[0].signal == "RSI_OVERBOUGHT"
    assert opps[0].suggested_trade is None  # notify only, not executable
