from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

from agents.models import AgentConfig, ActionLevel
from broker.models import Symbol, OrderSide


def _make_config(**overrides) -> AgentConfig:
    params = {"bb_period": 20, "bb_std": 2.0, "rsi_threshold": 35, "rsi_period": 14}
    params.update(overrides)
    return AgentConfig(
        name="mr_test",
        strategy="mean_reversion",
        schedule="cron",
        action_level=ActionLevel.NOTIFY,
        universe=["AAPL"],
        parameters=params,
    )


async def test_detects_oversold():
    from strategies.mean_reversion import MeanReversionAgent

    agent = MeanReversionAgent(_make_config())

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_quote = AsyncMock(
        return_value=MagicMock(last=MagicMock(__float__=lambda s: 140.0))
    )
    data.get_bollinger = AsyncMock(
        return_value=MagicMock(lower=145.0, middle=155.0, upper=165.0)
    )
    data.get_rsi = AsyncMock(return_value=28.0)

    opps = await agent.scan(data)
    assert len(opps) == 1
    assert opps[0].signal == "MEAN_REVERSION_OVERSOLD"
    assert opps[0].suggested_trade is not None
    assert opps[0].suggested_trade.side == OrderSide.BUY


async def test_no_signal_above_band():
    from strategies.mean_reversion import MeanReversionAgent

    agent = MeanReversionAgent(_make_config())

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_quote = AsyncMock(
        return_value=MagicMock(last=MagicMock(__float__=lambda s: 160.0))
    )
    data.get_bollinger = AsyncMock(
        return_value=MagicMock(lower=145.0, middle=155.0, upper=165.0)
    )
    data.get_rsi = AsyncMock(return_value=28.0)

    opps = await agent.scan(data)
    assert len(opps) == 0


async def test_no_signal_rsi_too_high():
    from strategies.mean_reversion import MeanReversionAgent

    agent = MeanReversionAgent(_make_config())

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_quote = AsyncMock(
        return_value=MagicMock(last=MagicMock(__float__=lambda s: 140.0))
    )
    data.get_bollinger = AsyncMock(
        return_value=MagicMock(lower=145.0, middle=155.0, upper=165.0)
    )
    data.get_rsi = AsyncMock(return_value=45.0)  # too high

    opps = await agent.scan(data)
    assert len(opps) == 0
