import pytest
from unittest.mock import MagicMock, AsyncMock

from integrations.bittensor.signals import (
    BittensorSignalPayload,
    create_bittensor_agent_signal,
)
from strategies.bittensor_consensus import BittensorAlphaAgent
from storage.symbol_map import SignalMapper
from agents.models import AgentConfig, ActionLevel


@pytest.fixture
def mock_signal_bus():
    bus = MagicMock()
    bus.publish = AsyncMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def agent_config():
    return AgentConfig(
        name="bt_agent",
        strategy="bittensor_consensus",
        schedule="continuous",
        interval=30,
        action_level=ActionLevel.SUGGEST_TRADE,
        universe=["BTC/USD", "ETH/USD"],
        parameters={"min_agreement": 0.7, "min_return": 0.01},
    )


def test_signal_mapper():
    mapper = SignalMapper()
    symbol = mapper.map_to_symbol("BTCUSD")
    assert symbol is not None
    assert symbol.ticker == "BTC/USD"

    symbol = mapper.map_to_symbol("EURUSD")
    assert symbol.ticker == "EUR/USD"


@pytest.mark.asyncio
async def test_bittensor_agent_handles_signal(agent_config, mock_signal_bus):
    agent = BittensorAlphaAgent(agent_config)
    agent.emit_opportunity = AsyncMock()

    # Create a bullish signal
    payload = BittensorSignalPayload(
        symbol="BTCUSD",
        timeframe="5m",
        direction="bullish",
        confidence=0.8,
        expected_return=0.02,
        window_id="test-1",
        miner_count=100,
    )
    signal = create_bittensor_agent_signal(payload)

    await agent.handle_signal(signal)

    assert len(agent._pending_opportunities) > 0
    opp = agent._pending_opportunities[0]
    assert opp.symbol.ticker == "BTC/USD"
    assert opp.signal == "BULLISH"
    assert opp.confidence == 0.8


@pytest.mark.asyncio
async def test_bittensor_agent_ignores_low_confidence(agent_config, mock_signal_bus):
    agent = BittensorAlphaAgent(agent_config)
    agent.emit_opportunity = AsyncMock()

    # Low confidence signal (0.5 < 0.7)
    payload = BittensorSignalPayload(
        symbol="BTCUSD",
        timeframe="5m",
        direction="bullish",
        confidence=0.5,
        expected_return=0.02,
        window_id="test-1",
        miner_count=100,
    )
    signal = create_bittensor_agent_signal(payload)

    await agent.handle_signal(signal)
    assert len(agent._pending_opportunities) == 0
