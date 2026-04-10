"""Integration tests for Agent Concurrency Limits."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.models import ActionLevel, AgentConfig
from agents.runner import AgentRunner


@pytest.fixture
def mock_data_bus():
    return MagicMock()


@pytest.fixture
def mock_router():
    router = MagicMock()
    router.route = AsyncMock()
    return router


class TestAgentConcurrencyIntegration:
    """Integration tests for agent concurrency limits."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_execution(
        self, mock_data_bus, mock_router
    ):
        """Test that semaphore correctly limits concurrent agent scans."""
        execution_order = []

        async def make_scan_fn(name, delay):
            async def scan(data_bus):
                execution_order.append(f"start_{name}")
                await asyncio.sleep(delay)
                execution_order.append(f"end_{name}")
                return []

            return scan

        runner = AgentRunner(
            data_bus=mock_data_bus,
            router=mock_router,
            max_concurrent_scans=2,
        )

        # Create 3 agents with different delays
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
                scan_timeout=10.0,
            )
            agent.scan = await make_scan_fn(f"agent_{i}", 0.1)
            agent.setup = AsyncMock()
            agent.teardown = AsyncMock()
            runner.register(agent)

        # Run all 3 agents concurrently
        await asyncio.gather(
            runner._execute_scan(runner._agents["agent_0"]),
            runner._execute_scan(runner._agents["agent_1"]),
            runner._execute_scan(runner._agents["agent_2"]),
        )

        # All should complete
        assert len(execution_order) == 6  # 3 starts + 3 ends

    @pytest.mark.asyncio
    async def test_scan_timeout_triggers_error(self, mock_data_bus, mock_router):
        """Test that scan timeout triggers error and increments error count."""

        async def slow_scan(data_bus):
            await asyncio.sleep(10)  # Longer than timeout
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
    async def test_default_timeout_used_when_not_configured(
        self, mock_data_bus, mock_router
    ):
        """Test that default timeout is used when agent doesn't specify one."""
        call_times = []

        async def tracked_scan(data_bus):
            call_times.append(asyncio.get_event_loop().time())
            return []

        agent = MagicMock()
        agent.name = "no_timeout_agent"
        agent.description = "Agent without timeout"
        agent.config = AgentConfig(
            name="no_timeout_agent",
            strategy="test_strategy",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
            interval=60,
            universe=["SPY"],
            # No scan_timeout specified
        )
        agent.scan = tracked_scan
        agent.setup = AsyncMock()
        agent.teardown = AsyncMock()

        runner = AgentRunner(
            data_bus=mock_data_bus,
            router=mock_router,
            default_scan_timeout=5.0,
        )
        runner.register(agent)

        result = await runner._execute_scan(agent)

        # Should complete successfully with default timeout
        assert result == []
        assert len(call_times) == 1

    @pytest.mark.asyncio
    async def test_multiple_agents_with_mixed_timeouts(
        self, mock_data_bus, mock_router
    ):
        """Test that agents with different timeouts work correctly."""
        results = {}

        async def make_scan_fn(name, should_succeed):
            async def scan(data_bus):
                if not should_succeed:
                    await asyncio.sleep(10)  # Will timeout
                results[name] = "completed"
                return []

            return scan

        runner = AgentRunner(
            data_bus=mock_data_bus,
            router=mock_router,
            default_scan_timeout=5.0,
        )

        # Agent with short timeout (will fail)
        agent1 = MagicMock()
        agent1.name = "fast_agent"
        agent1.description = "Fast agent"
        agent1.config = AgentConfig(
            name="fast_agent",
            strategy="test_strategy",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
            interval=60,
            universe=["SPY"],
            scan_timeout=0.1,
        )
        agent1.scan = await make_scan_fn("fast_agent", False)
        agent1.setup = AsyncMock()
        agent1.teardown = AsyncMock()
        runner.register(agent1)

        # Agent with no timeout (will use default and succeed)
        agent2 = MagicMock()
        agent2.name = "slow_agent"
        agent2.description = "Slow agent"
        agent2.config = AgentConfig(
            name="slow_agent",
            strategy="test_strategy",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
            interval=60,
            universe=["SPY"],
        )
        agent2.scan = await make_scan_fn("slow_agent", True)
        agent2.setup = AsyncMock()
        agent2.teardown = AsyncMock()
        runner.register(agent2)

        # Run both
        await asyncio.gather(
            runner._execute_scan(agent1),
            runner._execute_scan(agent2),
        )

        # Only slow_agent should have completed
        assert "slow_agent" in results
        assert "fast_agent" not in results
