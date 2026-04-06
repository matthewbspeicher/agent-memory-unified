"""Integration test: adapter -> SignalBus -> MetaAgent boost -> opportunity annotation."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.adapters.prediction_market import PredictionMarketAdapter
from agents.meta import MetaAgent
from agents.models import (
    ActionLevel,
    AgentConfig,
    AgentInfo,
    AgentStatus,
    Opportunity,
)
from agents.signal_adapter import SignalAdapterRunner
from broker.models import Symbol
from data.signal_bus import SignalBus


class FakeRunner:
    def __init__(self, agents: dict[str, AgentConfig]):
        self._agents = agents

    def list_agents(self):
        return [
            AgentInfo(name=n, description="", status=AgentStatus.RUNNING, config=c)
            for n, c in self._agents.items()
        ]

    def get_agent_info(self, name):
        c = self._agents.get(name)
        if c:
            return AgentInfo(
                name=name, description="", status=AgentStatus.RUNNING, config=c
            )
        return None

    def register(self, agent):
        pass


@pytest.mark.asyncio
async def test_full_signal_flow():
    """Adapter poll -> SignalBus -> MetaAgent boost -> signal cache for annotation."""
    signal_bus = SignalBus()

    arb_config = AgentConfig(
        name="kalshi_arb",
        strategy="arb",
        schedule="continuous",
        action_level=ActionLevel.AUTO_EXECUTE,
        universe=["AAPL-YES"],
        parameters={"confidence_threshold": 0.7},
    )
    runner = FakeRunner({"kalshi_arb": arb_config})

    meta_config = AgentConfig(
        name="meta_agent",
        strategy="meta",
        schedule="continuous",
        action_level=ActionLevel.NOTIFY,
        parameters={
            "boost_delta": 0.05,
            "max_cumulative_boost": 0.15,
            "boost_ttl_minutes": 15,
        },
    )
    meta = MetaAgent(config=meta_config, runner=runner, signal_bus=signal_bus)

    mock_data_bus = MagicMock()
    mock_data_bus.get_kalshi_markets = AsyncMock(
        return_value=[
            {"ticker": "AAPL-YES", "volume": 5000, "avg_volume": 1000, "yes_ask": 0.65},
        ]
    )
    adapter = PredictionMarketAdapter(
        data_bus=mock_data_bus, volume_spike_threshold=2.0
    )

    adapter_runner = SignalAdapterRunner(adapters=[adapter], signal_bus=signal_bus)

    # Poll the adapter — publishes to SignalBus -> MetaAgent handles it
    await adapter_runner.poll_once("prediction_market")

    # Verify: agent got boosted (bullish -> lower threshold)
    assert arb_config.runtime_overrides["confidence_threshold"] == 0.65

    # Verify: signal cached for annotation
    cached = meta.get_signals_for_ticker("AAPL-YES")
    assert len(cached) == 1
    assert cached[0].signal_type == "volume_anomaly"

    # Verify: annotation would work on an opportunity
    opp = Opportunity(
        id="test-opp-1",
        agent_name="kalshi_arb",
        symbol=Symbol(ticker="AAPL-YES"),
        signal="arb_spread",
        confidence=0.8,
        reasoning="test",
        data={},
        timestamp=datetime.now(timezone.utc),
    )
    ext_signals = meta.get_signals_for_ticker(opp.symbol.ticker)
    if ext_signals:
        opp.data["external_signals"] = [
            {"type": s.signal_type, "source": s.source_agent, "payload": s.payload}
            for s in ext_signals
        ]

    assert "external_signals" in opp.data
    assert opp.data["external_signals"][0]["type"] == "volume_anomaly"
