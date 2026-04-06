from __future__ import annotations
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal

from agents.models import AgentConfig, ActionLevel
from broker.models import Bar, OrderSide, Quote, Symbol


def _make_config(**overrides):
    defaults = dict(
        name="test_vol",
        strategy="volume_spike",
        schedule="cron",
        action_level=ActionLevel.AUTO_EXECUTE,
        parameters={"volume_threshold": 2.0},
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


def _bars(open_price: str, close_price: str) -> list[Bar]:
    sym = Symbol(ticker="AAPL")
    base = [
        Bar(
            symbol=sym,
            open=Decimal("150"),
            close=Decimal("150"),
            high=Decimal("151"),
            low=Decimal("149"),
            volume=1_000_000,
            timestamp=datetime(2026, 1, i + 1),
        )
        for i in range(19)
    ]
    # Most recent bar has the directional price action under test
    base.append(
        Bar(
            symbol=sym,
            open=Decimal(open_price),
            close=Decimal(close_price),
            high=Decimal("155"),
            low=Decimal("148"),
            volume=1_000_000,
            timestamp=datetime(2026, 1, 20),
        )
    )
    return base


async def test_volume_spike_with_positive_price_includes_buy():
    from strategies.volume_spike import VolumeSpikeAgent

    agent = VolumeSpikeAgent(_make_config())
    sym = Symbol(ticker="AAPL")

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[sym])
    # Bars: most recent bar is bullish (close > open)
    data.get_historical = AsyncMock(return_value=_bars("148", "152"))
    data.get_quote = AsyncMock(
        return_value=Quote(
            symbol=sym,
            last=Decimal("152"),
            volume=3_000_000,
            timestamp=datetime.now(),
        )
    )

    opps = await agent.scan(data)
    assert len(opps) == 1
    assert opps[0].signal == "VOLUME_SPIKE"
    assert opps[0].suggested_trade is not None
    assert opps[0].suggested_trade.side == OrderSide.BUY
    assert opps[0].suggested_trade.quantity == Decimal("1")


async def test_volume_spike_with_bearish_bar_no_trade():
    """Volume spike with bearish confirmation should NOT include a suggested_trade."""
    from strategies.volume_spike import VolumeSpikeAgent

    agent = VolumeSpikeAgent(_make_config())
    sym = Symbol(ticker="AAPL")

    data = MagicMock()
    data.get_universe = MagicMock(return_value=[sym])
    # Bars: most recent bar is bearish (close < open)
    data.get_historical = AsyncMock(return_value=_bars("155", "148"))
    data.get_quote = AsyncMock(
        return_value=Quote(
            symbol=sym,
            last=Decimal("148"),
            volume=3_000_000,
            timestamp=datetime.now(),
        )
    )

    opps = await agent.scan(data)
    assert len(opps) == 1
    assert opps[0].signal == "VOLUME_SPIKE"
    assert opps[0].suggested_trade is None  # no directional confirmation
