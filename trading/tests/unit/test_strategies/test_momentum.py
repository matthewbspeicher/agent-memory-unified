from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from agents.models import AgentConfig, ActionLevel
from broker.models import Bar, Symbol, OrderSide


def _make_bars(closes: list[float], volumes: list[int], symbol_ticker: str = "AAPL") -> list[Bar]:
    sym = Symbol(ticker=symbol_ticker)
    return [
        Bar(symbol=sym, close=Decimal(str(c)), volume=v, timestamp=datetime(2026, 3, 30, tzinfo=timezone.utc))
        for c, v in zip(closes, volumes)
    ]


def _make_config(**overrides) -> AgentConfig:
    params = {"lookback_days": 20, "volume_threshold": 1.5, "cooldown_hours": 24}
    params.update(overrides)
    return AgentConfig(
        name="momentum_test", strategy="momentum", schedule="cron",
        action_level=ActionLevel.NOTIFY,
        universe=["AAPL"],
        parameters=params,
    )


async def test_detects_momentum_breakout():
    from strategies.momentum import MomentumAgent

    agent = MomentumAgent(_make_config())

    # 20 bars where last bar breaks above all previous highs with 2x volume
    closes = [100 + i * 0.5 for i in range(20)] + [115.0]  # 21 bars, last is new high
    volumes = [1000] * 20 + [3000]  # last bar has 3x volume

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_historical = AsyncMock(return_value=_make_bars(closes, volumes))

    opps = await agent.scan(data)
    assert len(opps) == 1
    assert opps[0].signal == "MOMENTUM_BREAKOUT"
    assert opps[0].suggested_trade is not None
    assert opps[0].suggested_trade.side == OrderSide.BUY


async def test_no_signal_when_below_high():
    from strategies.momentum import MomentumAgent

    agent = MomentumAgent(_make_config())

    closes = [100 + i * 0.5 for i in range(20)] + [105.0]  # not a new high
    volumes = [1000] * 20 + [3000]

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_historical = AsyncMock(return_value=_make_bars(closes, volumes))

    opps = await agent.scan(data)
    assert len(opps) == 0


async def test_cooldown_prevents_repeat():
    from strategies.momentum import MomentumAgent

    agent = MomentumAgent(_make_config())

    closes = [100 + i * 0.5 for i in range(20)] + [115.0]
    volumes = [1000] * 20 + [3000]

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_historical = AsyncMock(return_value=_make_bars(closes, volumes))

    # First scan: should fire
    opps1 = await agent.scan(data)
    assert len(opps1) == 1

    # Second scan: cooldown prevents repeat
    opps2 = await agent.scan(data)
    assert len(opps2) == 0
