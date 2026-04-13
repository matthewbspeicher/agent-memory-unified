from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from agents.models import ActionLevel, AgentConfig, Opportunity

if TYPE_CHECKING:
    from data.bus import DataBus
    from data.signal_bus import SignalBus
    from learning.trade_reflector import TradeReflector


class Agent(ABC):
    # Gemini design §2.1: Strategy parameter schema for Hermes composition
    # Subclasses should override with their specific parameters
    PARAMETER_SCHEMA: dict[str, dict[str, Any]] = {}

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self.memory: TradeReflector | None = None  # injected by AgentRunner
        self.signal_bus: SignalBus | None = None  # injected by AgentRunner
        self._session_bias: Any | None = (
            None  # injected by AgentRunner (SessionBiasReport)
        )
        self._draining = False
        self._tv_context: Any | None = None  # TV context for agent
        self._drain_event: Any | None = None  # Event for graceful draining
        self._llm_call_count = 0

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def action_level(self) -> ActionLevel:
        return self._config.action_level

    @property
    def config(self) -> AgentConfig:
        return self._config

    @property
    def session_bias(self) -> Any | None:
        """Today's session bias report (injected by AgentRunner before scan)."""
        return self._session_bias

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    async def scan(self, data: DataBus) -> list[Opportunity]: ...

    async def setup(self) -> None:
        pass

    async def teardown(self) -> None:
        pass

    def reset_llm_call_count(self) -> None:
        self._llm_call_count = 0

    def increment_llm_call_count(self) -> None:
        self._llm_call_count += 1
        if self._llm_call_count > self._config.max_calls_per_scan:
            raise RuntimeError(
                f"Agent {self.name} exceeded max LLM calls per scan "
                f"({self._llm_call_count} > {self._config.max_calls_per_scan})"
            )


class StructuredAgent(Agent):
    @property
    def universe(self) -> list[str] | str:
        return self._config.universe

    @property
    def parameters(self) -> dict[str, Any]:
        return {**self._config.parameters, **self._config.runtime_overrides}

    async def structured_call(
        self,
        *,
        system_prompt: str,
        prompt: str,
        schema: dict[str, Any],
        llm_client: Any,
    ) -> dict[str, Any] | None:
        self.increment_llm_call_count()
        return await llm_client.structured_complete(
            prompt=prompt,
            schema=schema,
            system=system_prompt,
        )


class LLMAgent(Agent):
    def __init__(self, config: AgentConfig, prompt_store: Any = None) -> None:
        super().__init__(config)
        self._prompt_store = prompt_store

    @property
    def model(self) -> str:
        return self._config.model or "claude-sonnet-4-6"

    @property
    def system_prompt(self) -> str:
        base = self._config.system_prompt or ""
        context = ""
        if self._prompt_store:
            # L0 + L1 context (identity + performance story)
            agent_ctx = self._prompt_store.get_agent_context(self.name)
            if agent_ctx:
                context = agent_ctx
            # Learned rules from prompt versioning
            learned = self._prompt_store.get_runtime_prompt(self.name)
            if learned:
                context = f"{context}\n\n{learned}" if context else learned
        return f"{base}\n\n{context}" if context else base

    @property
    def tools(self) -> list[str]:
        return self._config.tools

    async def structured_call(
        self,
        *,
        system_prompt: str,
        prompt: str,
        schema: dict[str, Any],
        llm_client: Any,
    ) -> dict[str, Any] | None:
        self.increment_llm_call_count()
        return await llm_client.structured_complete(
            prompt=prompt,
            schema=schema,
            system=system_prompt,
        )
        return None
