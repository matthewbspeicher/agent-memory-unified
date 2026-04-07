import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone

from data.signal_bus import SignalBus
from integrations.bittensor.consensus_aggregator import MinerConsensusAggregator
from strategies.bittensor_consensus import BittensorAlphaAgent
from agents.models import AgentConfig, ActionLevel, AgentSignal
from agents.runner import AgentRunner

@pytest.mark.asyncio
async def test_bittensor_mock_e2e_loop():
    """
    E2E test:
    1. Spin up SignalBus
    2. Start MinerConsensusAggregator
    3. Register BittensorAlphaAgent
    4. Inject mock 'bittensor_miner_position' signals
    5. Wait for them to propagate into an Opportunity via the agent
    """
    signal_bus = SignalBus()

    # Configure agent with loose thresholds so it fires on mock signals
    agent_config = AgentConfig(
        name="bt_agent",
        strategy="bittensor_consensus",
        schedule="continuous",
        interval=1,
        action_level=ActionLevel.SUGGEST_TRADE,
        universe=["BTCUSD", "ETHUSD"],
        parameters={"min_agreement": 0.1, "min_return": 0.001},
    )
    agent = BittensorAlphaAgent(agent_config)
    agent.signal_bus = signal_bus
    await agent.setup()

    router = AsyncMock()
    runner = AgentRunner(data_bus=AsyncMock(), router=router)
    runner.register(agent)

    # Start Aggregator
    aggregator = MinerConsensusAggregator(signal_bus, window_minutes=5)
    await aggregator.start()

    # Simulate Bridge Emitting Miner Positions
    now = datetime.now(timezone.utc)
    base_payload = {
        "symbol": "BTCUSD",
        "leverage": 1.0,
        "price": 65000.0,
        "open_ms": int(now.timestamp() * 1000),
        "direction": "long",
        "miner_hotkey": "test_miner"
    }

    sig = AgentSignal(
        source_agent="taoshi_bridge",
        signal_type="bittensor_miner_position",
        payload=base_payload,
        expires_at=now + timedelta(minutes=30)
    )

    # Publish the raw position to the bus
    await signal_bus.publish(sig)

    # Give time for the aggregator to process and emit consensus, and agent to consume
    await asyncio.sleep(0.5)

    emitted_opps = await agent.scan(AsyncMock())

    await aggregator.stop()

    assert len(emitted_opps) > 0, "Agent did not emit any opportunities from aggregated signals"
    opp = emitted_opps[0]
    assert opp.agent_name == "bt_agent"
    assert opp.symbol.ticker == "BTC/USD"
    assert opp.signal in ["BULLISH", "BEARISH"]
