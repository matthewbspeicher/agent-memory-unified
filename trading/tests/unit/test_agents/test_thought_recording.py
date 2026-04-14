import pytest
from unittest.mock import AsyncMock, Mock
from agents.runner import AgentRunner
from agents.models import Opportunity
from models.thought import ActionType

@pytest.mark.asyncio
async def test_agent_records_thought():
    # Setup mock runner
    runner = AgentRunner(
        data_bus=AsyncMock(),
        router=AsyncMock(),
        event_bus=AsyncMock(),
        db=AsyncMock()
    )
    runner._record_thought = AsyncMock()

    # Mock Agent — set scan_timeout to None so asyncio.wait_for gets a real float
    mock_agent = AsyncMock()
    mock_agent.name = "test_agent"
    mock_agent.universe = ["BTC/USD"]
    mock_agent.config.broker = "mock_broker"
    mock_agent.config.scan_timeout = None
    mock_agent.action_level = "notify"
    # reset_llm_call_count is sync in real Agent — override AsyncMock default so
    # the coroutine isn't dropped unawaited (produces RuntimeWarning).
    mock_agent.reset_llm_call_count = Mock()

    # Mock opp — symbol needs a .ticker attribute (runner accesses opp.symbol.ticker)
    mock_opp = Mock(spec=Opportunity)
    mock_opp.symbol = Mock(ticker="BTC/USD")
    mock_opp.signal = "buy"
    mock_opp.confidence = 0.95
    mock_opp.broker_id = None

    mock_agent.scan = AsyncMock(return_value=[mock_opp])
    
    # Run _execute_scan
    await runner._execute_scan(mock_agent)
    
    # Assert _record_thought was called
    runner._record_thought.assert_called_once()
    args, kwargs = runner._record_thought.call_args
    assert kwargs["agent_name"] == "test_agent"
    assert kwargs["symbol"] == "BTC/USD"
    assert kwargs["action"] == ActionType.BUY
    assert kwargs["score"] == 0.95
