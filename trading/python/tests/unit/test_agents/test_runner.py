"""
Tests for agents/runner.py - AgentRunner with dependency injection
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from agents.runner import AgentRunner
from agents.base import Agent
from agents.models import AgentConfig, ActionLevel, Opportunity, OpportunityStatus
from broker.models import Symbol, AssetType


class MockAgent(Agent):
    """Mock agent for testing"""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.scan_called = False
        self.setup_called = False
        self.teardown_called = False

    async def setup(self) -> None:
        self.setup_called = True

    async def teardown(self) -> None:
        self.teardown_called = True

    async def scan(self, data_bus) -> list[Opportunity]:
        self.scan_called = True
        return []


class TestAgentRunnerDependencyInjection:
    """Test that AgentRunner accepts dependencies via constructor"""

    def test_accepts_data_bus_and_router(self):
        """Test that runner accepts data_bus and router dependencies"""
        mock_data_bus = MagicMock()
        mock_router = MagicMock()

        runner = AgentRunner(data_bus=mock_data_bus, router=mock_router)

        assert runner._data_bus == mock_data_bus
        assert runner._router == mock_router

    def test_accepts_optional_dependencies(self):
        """Test that runner accepts optional dependencies"""
        mock_data_bus = MagicMock()
        mock_router = MagicMock()
        mock_event_bus = MagicMock()
        mock_agent_store = MagicMock()

        runner = AgentRunner(
            data_bus=mock_data_bus,
            router=mock_router,
            event_bus=mock_event_bus,
            agent_store=mock_agent_store,
        )

        assert runner._event_bus == mock_event_bus
        assert runner._agent_store == mock_agent_store

    def test_registers_agent(self):
        """Test that runner can register agents"""
        mock_data_bus = MagicMock()
        mock_router = MagicMock()
        runner = AgentRunner(data_bus=mock_data_bus, router=mock_router)

        config = AgentConfig(
            name="test_agent",
            strategy="mock",
            schedule="continuous",
            interval=60,
            action_level=ActionLevel.NOTIFY,
            universe=["AAPL"],
            parameters={},
        )
        agent = MockAgent(config)

        runner.register(agent)

        assert "test_agent" in runner._agents
        assert runner.get_agent("test_agent") == agent

    @pytest.mark.asyncio
    async def test_run_once_executes_scan(self):
        """Test that run_once executes agent scan"""
        mock_data_bus = MagicMock()
        mock_router = MagicMock()
        mock_router.route = AsyncMock()

        runner = AgentRunner(data_bus=mock_data_bus, router=mock_router)

        config = AgentConfig(
            name="test_agent",
            strategy="mock",
            schedule="continuous",
            interval=60,
            action_level=ActionLevel.NOTIFY,
            universe=["AAPL"],
            parameters={},
        )
        agent = MockAgent(config)
        runner.register(agent)

        opportunities = await runner.run_once("test_agent")

        assert agent.scan_called
        assert opportunities == []


class TestAgentRunnerLifecycle:
    """Test agent lifecycle management"""

    @pytest.mark.asyncio
    async def test_start_agent_calls_setup(self):
        """Test that starting an agent calls setup"""
        mock_data_bus = MagicMock()
        mock_router = MagicMock()
        mock_router.route = AsyncMock()

        runner = AgentRunner(data_bus=mock_data_bus, router=mock_router)

        config = AgentConfig(
            name="test_agent",
            strategy="mock",
            schedule="continuous",
            interval=60,
            action_level=ActionLevel.NOTIFY,
            universe=["AAPL"],
            parameters={},
        )
        agent = MockAgent(config)
        runner.register(agent)

        await runner.start_agent("test_agent")

        assert agent.setup_called

    @pytest.mark.asyncio
    async def test_stop_agent_calls_teardown(self):
        """Test that stopping an agent calls teardown"""
        mock_data_bus = MagicMock()
        mock_router = MagicMock()
        mock_router.route = AsyncMock()

        runner = AgentRunner(data_bus=mock_data_bus, router=mock_router)

        config = AgentConfig(
            name="test_agent",
            strategy="mock",
            schedule="continuous",
            interval=60,
            action_level=ActionLevel.NOTIFY,
            universe=["AAPL"],
            parameters={},
        )
        agent = MockAgent(config)
        runner.register(agent)

        await runner.start_agent("test_agent")
        await runner.stop_agent("test_agent")

        assert agent.teardown_called
