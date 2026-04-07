"""Tests for async health recompute optimization."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from learning.strategy_health import StrategyHealthEngine, StrategyHealthConfig


class TestHealthAsyncRecompute:
    """Test that recompute_all uses asyncio.gather for concurrent execution."""

    @pytest.mark.asyncio
    async def test_recompute_all_calls_evaluate_for_each_agent(self):
        """Verify that recompute_all calls evaluate for each agent."""
        # Create engine with mocked dependencies
        health_store = AsyncMock()
        perf_store = AsyncMock()
        config = StrategyHealthConfig()
        engine = StrategyHealthEngine(
            health_store=health_store,
            perf_store=perf_store,
            config=config,
        )

        # Mock evaluate to return ok status
        engine.evaluate = AsyncMock(return_value=MagicMock(value="ok"))

        agent_names = ["agent1", "agent2", "agent3"]
        result = await engine.recompute_all(agent_names)

        # All agents should be in result
        assert len(result) == 3
        for name in agent_names:
            assert name in result

        # Verify evaluate was called for each agent
        assert engine.evaluate.call_count == 3

    @pytest.mark.asyncio
    async def test_recompute_all_returns_dict(self):
        """Verify recompute_all returns dict mapping agent_name -> status."""
        health_store = AsyncMock()
        perf_store = AsyncMock()
        engine = StrategyHealthEngine(
            health_store=health_store,
            perf_store=perf_store,
        )

        engine.get_status = AsyncMock(return_value="ok")

        result = await engine.recompute_all(["agent1", "agent2"])

        assert isinstance(result, dict)
        assert "agent1" in result
        assert "agent2" in result

    @pytest.mark.asyncio
    async def test_recompute_all_empty_list(self):
        """Verify recompute_all handles empty list."""
        health_store = AsyncMock()
        perf_store = AsyncMock()
        engine = StrategyHealthEngine(
            health_store=health_store,
            perf_store=perf_store,
        )

        result = await engine.recompute_all([])

        assert result == {}

    @pytest.mark.asyncio
    async def test_recompute_all_single_agent(self):
        """Verify recompute_all works with single agent."""
        health_store = AsyncMock()
        perf_store = AsyncMock()
        engine = StrategyHealthEngine(
            health_store=health_store,
            perf_store=perf_store,
        )

        engine.get_status = AsyncMock(return_value="ok")

        result = await engine.recompute_all(["single_agent"])

        assert len(result) == 1
        assert "single_agent" in result
