from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


from agents.base import StructuredAgent
from agents.config import _STRATEGY_REGISTRY, register_strategy
from agents.models import ActionLevel, AgentConfig, Opportunity


def _make_config(name: str = "test_agent", strategy: str = "fake") -> AgentConfig:
    return AgentConfig(
        name=name,
        strategy=strategy,
        schedule="on_demand",
        action_level=ActionLevel.NOTIFY,
    )


# ---------------------------------------------------------------------------
# Minimal concrete StructuredAgent subclasses used across the tests
# ---------------------------------------------------------------------------


class FakeAgent(StructuredAgent):
    description = "FakeAgent for tests"

    async def scan(self, data: Any) -> list[Opportunity]:  # type: ignore[override]
        return []


class FakeAgentWithDep(StructuredAgent):
    description = "FakeAgent that holds an injected dependency"

    def __init__(self, config: AgentConfig, dependency: Any) -> None:
        super().__init__(config)
        self.dependency = dependency

    async def scan(self, data: Any) -> list[Opportunity]:  # type: ignore[override]
        return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_register_strategy_accepts_callable():
    """A lambda that creates a FakeAgent can be registered and invoked."""
    factory = lambda config: FakeAgent(config=config)  # noqa: E731
    register_strategy("test_lambda_factory", factory)

    assert "test_lambda_factory" in _STRATEGY_REGISTRY
    config = _make_config(strategy="test_lambda_factory")
    agent = _STRATEGY_REGISTRY["test_lambda_factory"](config)
    assert isinstance(agent, FakeAgent)
    assert agent.config is config


def test_register_strategy_closure_with_injection():
    """A closure that captures a mock dependency injects it into the agent."""
    mock_dep = MagicMock(name="mock_dependency")

    def make_factory(dep: Any):
        def factory(config: AgentConfig) -> FakeAgentWithDep:
            return FakeAgentWithDep(config=config, dependency=dep)

        return factory

    register_strategy("test_closure_factory", make_factory(mock_dep))

    assert "test_closure_factory" in _STRATEGY_REGISTRY
    config = _make_config(strategy="test_closure_factory")
    agent = _STRATEGY_REGISTRY["test_closure_factory"](config)
    assert isinstance(agent, FakeAgentWithDep)
    assert agent.dependency is mock_dep


def test_register_strategy_still_accepts_class():
    """Registering a plain class (old-style) still works for backward compat."""
    register_strategy("test_plain_class", FakeAgent)

    assert "test_plain_class" in _STRATEGY_REGISTRY
    config = _make_config(strategy="test_plain_class")
    agent = _STRATEGY_REGISTRY["test_plain_class"](config=config)
    assert isinstance(agent, FakeAgent)
    assert agent.config.name == "test_agent"
