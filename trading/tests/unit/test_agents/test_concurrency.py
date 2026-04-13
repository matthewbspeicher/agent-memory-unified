"""Tests for AgentRunner concurrency limits."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.models import ActionLevel, AgentConfig, AgentStatus
from agents.runner import AgentRunner


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.description = "Test agent"
    agent.config = AgentConfig(
        name="test_agent",
        strategy="test_strategy",
        schedule="continuous",
        action_level=ActionLevel.NOTIFY,
        interval=60,
        universe=["SPY"],
        scan_timeout=10.0,
    )
    agent.scan = AsyncMock(return_value=[])
    agent.setup = AsyncMock()
    agent.teardown = AsyncMock()
    return agent


@pytest.fixture
def mock_data_bus():
    return MagicMock()


@pytest.fixture
def mock_router():
    router = MagicMock()
    router.route = AsyncMock()
    return router


class TestAgentConcurrencyLimits:
    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_scans(
        self, mock_agent, mock_data_bus, mock_router
    ):
        runner = AgentRunner(
            data_bus=mock_data_bus,
            router=mock_router,
            max_concurrent_scans=2,
        )
        runner.register(mock_agent)

        # Verify semaphore is initialized with correct limit
        assert runner._scan_semaphore._value == 2

    @pytest.mark.asyncio
    async def test_default_scan_timeout(self, mock_agent, mock_data_bus, mock_router):
        runner = AgentRunner(
            data_bus=mock_data_bus,
            router=mock_router,
            default_scan_timeout=60.0,
        )
        assert runner._default_scan_timeout == 60.0

    @pytest.mark.asyncio
    async def test_scan_timeout_from_agent_config(
        self, mock_agent, mock_data_bus, mock_router
    ):
        mock_agent.config.scan_timeout = 30.0
        runner = AgentRunner(
            data_bus=mock_data_bus,
            router=mock_router,
            default_scan_timeout=120.0,
        )
        runner.register(mock_agent)

        await runner._execute_scan(mock_agent)

        # Verify timeout was used (agent.config.scan_timeout=30.0)
        mock_agent.scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_timeout_fallback_to_default(self, mock_data_bus, mock_router):
        agent = MagicMock()
        agent.name = "no_timeout_agent"
        agent.description = "Agent without scan_timeout"
        agent.config = AgentConfig(
            name="no_timeout_agent",
            strategy="test_strategy",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
            interval=60,
            universe=["SPY"],
        )
        agent.scan = AsyncMock(return_value=[])
        agent.setup = AsyncMock()
        agent.teardown = AsyncMock()

        runner = AgentRunner(
            data_bus=mock_data_bus,
            router=mock_router,
            default_scan_timeout=45.0,
        )
        runner.register(agent)

        await runner._execute_scan(agent)

        agent.scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_timeout_triggers_error_on_exceed(
        self, mock_data_bus, mock_router
    ):
        async def slow_scan(*args, **kwargs):
            await asyncio.sleep(10)
            return []

        agent = MagicMock()
        agent.name = "slow_agent"
        agent.description = "Slow agent"
        agent.config = AgentConfig(
            name="slow_agent",
            strategy="test_strategy",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
            interval=60,
            universe=["SPY"],
            scan_timeout=0.1,  # Very short timeout
        )
        agent.scan = slow_scan
        agent.setup = AsyncMock()
        agent.teardown = AsyncMock()

        runner = AgentRunner(
            data_bus=mock_data_bus,
            router=mock_router,
        )
        runner.register(agent)

        result = await runner._execute_scan(agent)

        # Should return empty list on timeout
        assert result == []
        # Error count should be incremented
        assert runner._error_counts["slow_agent"] == 1
        assert "timeout" in runner._last_errors["slow_agent"].lower()

    @pytest.mark.asyncio
    async def test_multiple_agents_respect_semaphore(self, mock_data_bus, mock_router):
        call_order = []

        async def make_scan_fn(agent_name):
            async def scan_fn(data_bus):
                call_order.append(f"start_{agent_name}")
                await asyncio.sleep(0.1)
                call_order.append(f"end_{agent_name}")
                return []

            return scan_fn

        runner = AgentRunner(
            data_bus=mock_data_bus,
            router=mock_router,
            max_concurrent_scans=2,
        )

        # Register 3 agents
        for i in range(3):
            agent = MagicMock()
            agent.name = f"agent_{i}"
            agent.description = f"Agent {i}"
            agent.config = AgentConfig(
                name=f"agent_{i}",
                strategy="test_strategy",
                schedule="continuous",
                action_level=ActionLevel.NOTIFY,
                interval=60,
                universe=["SPY"],
                scan_timeout=5.0,
            )
            agent.scan = await make_scan_fn(agent.name)
            agent.setup = AsyncMock()
            agent.teardown = AsyncMock()
            runner.register(agent)

        # Run all 3 concurrently
        await asyncio.gather(
            runner._execute_scan(runner._agents["agent_0"]),
            runner._execute_scan(runner._agents["agent_1"]),
            runner._execute_scan(runner._agents["agent_2"]),
        )

        # All should complete
        assert len(call_order) == 6  # 3 starts + 3 ends
