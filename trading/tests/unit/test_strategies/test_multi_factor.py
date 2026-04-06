from __future__ import annotations
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from agents.models import AgentConfig, ActionLevel
from broker.models import Symbol, OrderSide


def _make_bars(
    count: int = 36, base_close: Decimal = Decimal("100"), final_volume: int = 4000
):
    bars = [
        MagicMock(
            close=base_close + Decimal(str(i)),
            high=base_close + Decimal(str(i + 1)),
            low=base_close + Decimal(str(i - 1)),
            volume=1000,
        )
        for i in range(count - 1)
    ]
    bars.append(
        MagicMock(
            close=base_close + Decimal(str(count)),
            high=base_close + Decimal(str(count + 1)),
            low=base_close + Decimal(str(count - 1)),
            volume=final_volume,
        )
    )
    return bars


async def test_strong_composite_fires(monkeypatch):
    import strategies.multi_factor as multi_factor_module

    MultiFactorAgent = multi_factor_module.MultiFactorAgent

    config = AgentConfig(
        name="mf_test",
        strategy="multi_factor",
        schedule="cron",
        action_level=ActionLevel.NOTIFY,
        universe=["AAPL"],
        parameters={
            "composite_threshold": 0.6,
            "rsi_weight": 0.4,
            "macd_weight": 0.3,
            "volume_weight": 0.3,
        },
    )
    agent = MultiFactorAgent(config)

    monkeypatch.setattr(multi_factor_module, "compute_rsi", lambda bars, period: 25.0)
    monkeypatch.setattr(
        multi_factor_module,
        "compute_macd",
        lambda bars: MagicMock(macd_line=50.0, signal_line=0.0),
    )

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_historical = AsyncMock(return_value=_make_bars(final_volume=8000))

    opps = await agent.scan(data)
    assert len(opps) == 1
    assert opps[0].signal == "MULTI_FACTOR_BUY"
    assert opps[0].suggested_trade.side == OrderSide.BUY


async def test_weak_composite_no_signal(monkeypatch):
    import strategies.multi_factor as multi_factor_module

    MultiFactorAgent = multi_factor_module.MultiFactorAgent

    config = AgentConfig(
        name="mf_test",
        strategy="multi_factor",
        schedule="cron",
        action_level=ActionLevel.NOTIFY,
        universe=["AAPL"],
        parameters={
            "composite_threshold": 0.6,
            "rsi_weight": 0.4,
            "macd_weight": 0.3,
            "volume_weight": 0.3,
        },
    )
    agent = MultiFactorAgent(config)

    monkeypatch.setattr(multi_factor_module, "compute_rsi", lambda bars, period: 50.0)
    monkeypatch.setattr(
        multi_factor_module,
        "compute_macd",
        lambda bars: MagicMock(macd_line=0.1, signal_line=0.1),
    )

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_historical = AsyncMock(return_value=_make_bars(final_volume=1000))

    opps = await agent.scan(data)
    assert len(opps) == 0


async def test_no_sell_signals(monkeypatch):
    """MultiFactorAgent should only emit BUY in Phase 1."""
    import strategies.multi_factor as multi_factor_module

    MultiFactorAgent = multi_factor_module.MultiFactorAgent

    config = AgentConfig(
        name="mf_test",
        strategy="multi_factor",
        schedule="cron",
        action_level=ActionLevel.NOTIFY,
        universe=["AAPL"],
        parameters={
            "composite_threshold": 0.6,
            "rsi_weight": 0.4,
            "macd_weight": 0.3,
            "volume_weight": 0.3,
        },
    )
    agent = MultiFactorAgent(config)

    monkeypatch.setattr(multi_factor_module, "compute_rsi", lambda bars, period: 80.0)
    monkeypatch.setattr(
        multi_factor_module,
        "compute_macd",
        lambda bars: MagicMock(macd_line=-1.5, signal_line=-0.5),
    )

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_historical = AsyncMock(return_value=_make_bars(final_volume=500))

    opps = await agent.scan(data)
    # Even with strong bearish composite, no SELL signal in Phase 1
    assert all(opp.signal != "MULTI_FACTOR_SELL" for opp in opps)


async def test_insufficient_bars_skips_without_indicator_calls(monkeypatch):
    import strategies.multi_factor as multi_factor_module

    MultiFactorAgent = multi_factor_module.MultiFactorAgent

    config = AgentConfig(
        name="mf_test",
        strategy="multi_factor",
        schedule="cron",
        action_level=ActionLevel.NOTIFY,
        universe=["AAPL"],
        parameters={"lookback_days": 20, "rsi_period": 14},
    )
    agent = MultiFactorAgent(config)

    compute_rsi_mock = MagicMock()
    compute_macd_mock = MagicMock()
    monkeypatch.setattr(multi_factor_module, "compute_rsi", compute_rsi_mock)
    monkeypatch.setattr(multi_factor_module, "compute_macd", compute_macd_mock)

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
    data.get_historical = AsyncMock(return_value=_make_bars(count=21))

    opps = await agent.scan(data)

    assert opps == []
    compute_rsi_mock.assert_not_called()
    compute_macd_mock.assert_not_called()
