from unittest.mock import AsyncMock, MagicMock
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
    agent.scan = AsyncMock(return_value=[])

    runner.register(agent)
    await runner.run_once("test_agent")

    emitter.heartbeat.assert_awaited_once_with(
        agent_name="test_agent",
        status="running",
        cycle_count=1,
    )
