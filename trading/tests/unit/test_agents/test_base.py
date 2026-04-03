from unittest.mock import MagicMock
import pytest

from agents.base import Agent, StructuredAgent, LLMAgent
from agents.models import ActionLevel, AgentConfig


class TestAgentABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            Agent(config=MagicMock())


class ConcreteStructuredAgent(StructuredAgent):
    """Test implementation."""
    @property
    def description(self) -> str:
        return "test agent"

    async def scan(self, data):
        return []


class TestStructuredAgent:
    def test_create(self):
        cfg = AgentConfig(
            name="test", strategy="test", schedule="on_demand",
            action_level=ActionLevel.NOTIFY, universe=["AAPL"],
            parameters={"threshold": 30},
        )
        agent = ConcreteStructuredAgent(config=cfg)
        assert agent.name == "test"
        assert agent.action_level == ActionLevel.NOTIFY
        assert agent.universe == ["AAPL"]
        assert agent.parameters == {"threshold": 30}

    async def test_scan_returns_list(self):
        cfg = AgentConfig(
            name="test", strategy="test", schedule="on_demand",
            action_level=ActionLevel.NOTIFY,
        )
        agent = ConcreteStructuredAgent(config=cfg)
        result = await agent.scan(MagicMock())
        assert result == []

    async def test_setup_teardown_are_noop(self):
        cfg = AgentConfig(
            name="test", strategy="test", schedule="on_demand",
            action_level=ActionLevel.NOTIFY,
        )
        agent = ConcreteStructuredAgent(config=cfg)
        await agent.setup()
        await agent.teardown()


class ConcreteLLMAgent(LLMAgent):
    """Concrete test implementation of LLMAgent."""
    @property
    def description(self) -> str:
        return "test llm agent"

    async def scan(self, data):
        return []


class TestLLMAgentClass:
    def test_llm_agent_system_prompt_with_prompt_store(self):
        """Test that system_prompt includes base and learned rules."""
        cfg = AgentConfig(
            name="analyst", strategy="test", schedule="on_demand",
            action_level=ActionLevel.NOTIFY,
            system_prompt="You are an analyst.",
        )
        mock_prompt_store = MagicMock()
        mock_prompt_store.get_runtime_prompt.return_value = "## Learned Rules\n- Always check earnings"

        agent = ConcreteLLMAgent(config=cfg, prompt_store=mock_prompt_store)

        assert agent.system_prompt == "You are an analyst.\n\n## Learned Rules\n- Always check earnings"
        mock_prompt_store.get_runtime_prompt.assert_called_once_with("analyst")

    def test_llm_agent_system_prompt_without_prompt_store(self):
        """Test that system_prompt returns just the base when no prompt_store."""
        cfg = AgentConfig(
            name="analyst", strategy="test", schedule="on_demand",
            action_level=ActionLevel.NOTIFY,
            system_prompt="You are an analyst.",
        )

        agent = ConcreteLLMAgent(config=cfg)

        assert agent.system_prompt == "You are an analyst."
