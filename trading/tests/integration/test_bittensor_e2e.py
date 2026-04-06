import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from data.signal_bus import SignalBus
from integrations.bittensor.mock_source import MockBittensorSource
from strategies.bittensor_consensus import BittensorAlphaAgent
from agents.models import AgentConfig, ActionLevel
from agents.runner import AgentRunner


@pytest.mark.asyncio
async def test_bittensor_mock_e2e_loop():
    """
    E2E test:
    1. Spin up SignalBus
    2. Start MockBittensorSource (non-blocking)
    3. Register BittensorAlphaAgent
    4. Wait for a signal to propagate into an Opportunity
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

    # Setup the agent (subscribes to signal_bus)
    agent.signal_bus = signal_bus
    await agent.setup()

    # Setup a mock runner
    router = AsyncMock()
    runner = AgentRunner(data_bus=AsyncMock(), router=router)
    runner.register(agent)

    # Mock source
    mock_source = MockBittensorSource(signal_bus, symbols=["BTCUSD"])

    with patch("random.uniform", return_value=0.5):
        # Run the source in background for a short tick, forcing a random signal
        task = asyncio.create_task(mock_source.start(interval_seconds=0.1))

        try:
            # Wait a little for signals to be emitted and handled
            await asyncio.sleep(0.5)
        finally:
            mock_source.stop()
            task.cancel()

    # Agent should have received signals and stored pending opportunities
    # We call scan to retrieve them
    emitted_opps = await agent.scan(AsyncMock())

    assert len(emitted_opps) > 0, (
        "Agent did not emit any opportunities from mock source"
    )

    opp = emitted_opps[0]
    assert opp.agent_name == "bt_agent"
    assert opp.symbol.ticker == "BTC/USD"
    assert opp.signal in ["BULLISH", "BEARISH"]
