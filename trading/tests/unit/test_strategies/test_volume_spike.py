from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest

from agents.models import ActionLevel, AgentConfig
from broker.models import Bar, Quote, Symbol
from strategies.volume_spike import VolumeSpikeAgent


def _make_config(**overrides):
    defaults = dict(
        name="vol-test", strategy="volume_spike", schedule="on_demand",
        action_level=ActionLevel.NOTIFY, universe=["AAPL"],
        parameters={"volume_threshold": 2.0},
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


def _make_bars_with_volume(volumes: list[int]) -> list[Bar]:
    sym = Symbol(ticker="AAPL")
    return [
        Bar(symbol=sym, close=Decimal("150"), open=Decimal("150"),
            high=Decimal("151"), low=Decimal("149"), volume=v,
            timestamp=datetime(2026, 1, i + 1))
        for i, v in enumerate(volumes)
    ]


class TestVolumeSpikeAgent:
    async def test_detects_spike(self):
        bus = MagicMock()
        bus.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
        # Average volume ~1M, current quote volume 3M = 3x spike
        bus.get_historical = AsyncMock(return_value=_make_bars_with_volume([1_000_000] * 20))
        bus.get_quote = AsyncMock(return_value=Quote(
            symbol=Symbol(ticker="AAPL"), last=Decimal("150"),
            volume=3_000_000, timestamp=datetime.now(),
        ))

        agent = VolumeSpikeAgent(config=_make_config())
        opps = await agent.scan(bus)

        assert len(opps) == 1
        assert opps[0].signal == "VOLUME_SPIKE"
        assert opps[0].data["volume_ratio"] >= 2.0

    async def test_no_spike(self):
        bus = MagicMock()
        bus.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
        bus.get_historical = AsyncMock(return_value=_make_bars_with_volume([1_000_000] * 20))
        bus.get_quote = AsyncMock(return_value=Quote(
            symbol=Symbol(ticker="AAPL"), last=Decimal("150"),
            volume=1_200_000, timestamp=datetime.now(),
        ))

        agent = VolumeSpikeAgent(config=_make_config())
        opps = await agent.scan(bus)
        assert len(opps) == 0
