from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from agents.runner import AgentRunner
from agents.models import ActionLevel


def _make_runner_with_emitter():
    data_bus = MagicMock()
    router = MagicMock()
    router.route = AsyncMock()
    emitter = MagicMock()
    emitter.heartbeat = AsyncMock()
    runner = AgentRunner(data_bus=data_bus, router=router, emitter=emitter)
    return runner, emitter


@pytest.mark.asyncio
async def test_heartbeat_called_after_successful_scan():
    runner, emitter = _make_runner_with_emitter()

    agent = MagicMock()
    agent.name = "test_agent"
    agent.description = "test"
    agent.action_level = ActionLevel.NOTIFY
    agent.config = MagicMock()
    agent.config.scan_timeout = None  # Ensure getattr returns None, not MagicMock
    agent.config.universe = ["SPY"]
    agent.scan = AsyncMock(return_value=[])
    agent.scan_with_guards = AsyncMock(return_value=[])

    runner.register(agent)

    # Mock the thought module to avoid sqlmodel import
    mock_thought = MagicMock()
    mock_thought.ActionType.HOLD = "hold"
    mock_thought.ActionType.BUY = "buy"
    mock_thought.ActionType.SELL = "sell"

    with patch.dict("sys.modules", {"models.thought": mock_thought}):
        await runner.run_once("test_agent")

    emitter.heartbeat.assert_awaited_once_with(
        agent_name="test_agent",
        status="running",
        cycle_count=1,
    )
