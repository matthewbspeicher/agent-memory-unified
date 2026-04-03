import pytest
from unittest.mock import MagicMock, patch

from agents.tuning import AdaptiveTuner
from agents.models import AgentConfig, ActionLevel, AgentInfo, AgentStatus


class MockRunner:
    def __init__(self, configs):
        self.configs = configs

    def get_agent_info(self, name):
        if name in self.configs:
            return AgentInfo(
                name=name,
                description="Mock",
                status=AgentStatus.RUNNING,
                config=self.configs[name],
            )
        return None

    def list_agents(self):
        return [self.get_agent_info(name) for name in self.configs]


class MockOppStore:
    def __init__(self, data):
        self.data = data

    async def list(
        self, agent_name=None, symbol=None, signal=None, status=None, limit=50
    ):
        return self.data.get(agent_name, [])


@pytest.mark.asyncio
async def test_adaptive_tuner_tightens_threshold():
    # Setup poor performing agent data (4 executions, 16 rejections = 20% rate, 20 total)
    opps = [{"status": "executed"} for _ in range(4)] + [
        {"status": "rejected"} for _ in range(16)
    ]
    opp_store = MockOppStore({"agent_poor": opps})

    config = AgentConfig(
        name="agent_poor",
        strategy="dummy",
        schedule="on_demand",
        action_level=ActionLevel.AUTO_EXECUTE,
        parameters={"confidence_threshold": 0.5},
    )
    runner = MockRunner({"agent_poor": config})

    tuner = AdaptiveTuner(runner=runner, opp_store=opp_store, trade_store=None)  # type: ignore

    # Run tuning cycle
    await tuner.run_tuning_cycle()

    # 20% win rate (< 0.4) should tighten (increase) threshold by 0.05
    assert (
        runner.configs["agent_poor"].runtime_overrides["confidence_threshold"] == 0.55
    )


@pytest.mark.asyncio
async def test_adaptive_tuner_loosens_threshold():
    # Setup high performing agent data (14 executions, 6 rejections = 70% rate, 20 total)
    opps = [{"status": "executed"} for _ in range(14)] + [
        {"status": "rejected"} for _ in range(6)
    ]
    opp_store = MockOppStore({"agent_good": opps})

    config = AgentConfig(
        name="agent_good",
        strategy="dummy",
        schedule="on_demand",
        action_level=ActionLevel.AUTO_EXECUTE,
        parameters={"confidence_threshold": 0.8},
    )
    runner = MockRunner({"agent_good": config})

    tuner = AdaptiveTuner(runner=runner, opp_store=opp_store, trade_store=None)  # type: ignore

    # Run tuning cycle
    await tuner.run_tuning_cycle()

    # 70% win rate (> 0.6) should loosen (decrease) threshold by 0.05
    assert (
        runner.configs["agent_good"].runtime_overrides["confidence_threshold"] == 0.75
    )


@pytest.mark.asyncio
async def test_generate_recommendations_fallback():
    tuner = AdaptiveTuner(runner=None, opp_store=None, trade_store=None)  # type: ignore
    # Mock the unified LLM client to raise an exception
    with patch.object(tuner._llm, "complete", side_effect=Exception("no provider")):
        result = await tuner.generate_recommendations(
            "test_agent",
            {
                "win_rate": 0.3,
                "sharpe_ratio": -0.2,
                "max_drawdown": 0.15,
                "total_trades": 10,
            },
        )
    assert result
    assert "threshold" in result.lower()


@pytest.mark.asyncio
async def test_generate_recommendations_uses_anthropic():
    tuner = AdaptiveTuner(runner=None, opp_store=None, trade_store=None)  # type: ignore
    # Mock the unified LLM client's complete method
    mock_result = MagicMock()
    mock_result.text = "Use RSI threshold 0.65."
    with patch.object(tuner._llm, "complete", return_value=mock_result):
        result = await tuner.generate_recommendations(
            "test_agent",
            {
                "win_rate": 0.55,
                "sharpe_ratio": 0.8,
                "max_drawdown": 0.05,
                "total_trades": 50,
            },
        )
    assert result == "Use RSI threshold 0.65."


@pytest.mark.asyncio
async def test_generate_recommendations_poor_performance():
    tuner = AdaptiveTuner(runner=None, opp_store=None, trade_store=None)  # type: ignore
    result = await tuner.generate_recommendations(
        "poor_agent",
        {
            "win_rate": 0.2,
            "sharpe_ratio": -0.5,
            "max_drawdown": 0.3,
            "total_trades": 20,
        },
    )
    assert "threshold" in result.lower()


@pytest.mark.asyncio
async def test_adaptive_tuner_skips_small_sample():
    """With fewer than 20 data points, tuner should not adjust threshold."""
    opps = [{"status": "executed"} for _ in range(2)] + [
        {"status": "rejected"} for _ in range(8)
    ]
    opp_store = MockOppStore({"agent_small": opps})

    config = AgentConfig(
        name="agent_small",
        strategy="dummy",
        schedule="on_demand",
        action_level=ActionLevel.AUTO_EXECUTE,
        parameters={"confidence_threshold": 0.5},
    )
    runner = MockRunner({"agent_small": config})

    tuner = AdaptiveTuner(runner=runner, opp_store=opp_store, trade_store=None)  # type: ignore
    await tuner.tune_agent("agent_small")

    # 10 data points < 20 min sample — should NOT adjust
    assert "confidence_threshold" not in runner.configs["agent_small"].runtime_overrides
