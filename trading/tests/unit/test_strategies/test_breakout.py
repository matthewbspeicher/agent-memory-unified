from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from agents.models import AgentConfig, ActionLevel
from broker.models import Bar, Symbol, OrderSide


def _make_bars(closes, volumes, ticker="AAPL"):
    sym = Symbol(ticker=ticker)
    return [
        Bar(symbol=sym, close=Decimal(str(c)), volume=v, timestamp=datetime(2026, 3, 30, tzinfo=timezone.utc))
        for c, v in zip(closes, volumes)
    ]


async def test_detects_resistance_breakout():
    from strategies.breakout import BreakoutAgent

    config = AgentConfig(
        name="bo_test", strategy="breakout", schedule="cron",
        action_level=ActionLevel.NOTIFY,
        universe=["AAPL"],
        parameters={"lookback_days": 50, "volume_threshold": 2.0},
    )
    agent = BreakoutAgent(config)

    closes = [100 + (i % 10) * 0.5 for i in range(50)] + [110.0]  # last bar breaks above range
    volumes = [1000] * 50 + [5000]  # 5x volume

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_historical = AsyncMock(return_value=_make_bars(closes, volumes))

    opps = await agent.scan(data)
    assert len(opps) == 1
    assert opps[0].signal == "RESISTANCE_BREAKOUT"
    assert opps[0].suggested_trade.side == OrderSide.BUY


async def test_no_signal_insufficient_volume():
    from strategies.breakout import BreakoutAgent

    config = AgentConfig(
        name="bo_test", strategy="breakout", schedule="cron",
        action_level=ActionLevel.NOTIFY,
        universe=["AAPL"],
        parameters={"lookback_days": 50, "volume_threshold": 2.0},
    )
    agent = BreakoutAgent(config)

    closes = [100 + (i % 10) * 0.5 for i in range(50)] + [110.0]
    volumes = [1000] * 50 + [1500]  # only 1.5x — below 2.0 threshold

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_historical = AsyncMock(return_value=_make_bars(closes, volumes))

    opps = await agent.scan(data)
    assert len(opps) == 0


async def test_cooldown_prevents_repeat():
    from strategies.breakout import BreakoutAgent

    config = AgentConfig(
        name="bo_test", strategy="breakout", schedule="cron",
        action_level=ActionLevel.NOTIFY,
        universe=["AAPL"],
        parameters={"lookback_days": 50, "volume_threshold": 2.0, "cooldown_hours": 24},
    )
    agent = BreakoutAgent(config)

    closes = [100 + (i % 10) * 0.5 for i in range(50)] + [110.0]
    volumes = [1000] * 50 + [5000]

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_historical = AsyncMock(return_value=_make_bars(closes, volumes))

    opps1 = await agent.scan(data)
    assert len(opps1) == 1

    opps2 = await agent.scan(data)
    assert len(opps2) == 0
