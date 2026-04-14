"""AgentMemory — unified facade over all memory subsystems.

Provides a single `remember()` method that queries TradeReflector,
TradingMemoryClient, and PromptStore in parallel and composes a context
block suitable for injection into an agent's system prompt.

Usage::

    memory = AgentMemory(
        trade_reflector=reflector,
        memory_client=mem_client,
        prompt_store=pstore,
    )
    ctx = await memory.remember(
        agent_name="rsi_agent",
        query="BTC momentum signal",
        agent_config=config,
    )
    # ctx is a string ready for system prompt injection
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from learning.trade_reflector import TradeReflector
    from learning.memory_client import TradingMemoryClient
    from learning.prompt_store import PromptStore
    from agents.models import AgentConfig

logger = logging.getLogger(__name__)


@dataclass
class MemoryContext:
    """Composed memory context ready for prompt injection."""

    identity: str = ""
    rules: str = ""
    lessons: str = ""
    trade_memories: str = ""
    shared_observations: str = ""

    @property
    def full(self) -> str:
        sections = []
        if self.identity:
            sections.append(self.identity)
        if self.rules:
            sections.append(self.rules)
        if self.lessons:
            sections.append(self.lessons)
        if self.trade_memories:
            sections.append(self.trade_memories)
        if self.shared_observations:
            sections.append(self.shared_observations)
        return "\n\n".join(sections)

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.identity,
                self.rules,
                self.lessons,
                self.trade_memories,
                self.shared_observations,
            ]
        )


class AgentMemory:
    """Unified memory facade.

    Wraps TradeReflector (trade-specific memories), TradingMemoryClient
    (private + shared Remembr namespaces), and PromptStore (L0/L1 context
    + learned rules + recent lessons).

    All three backends are queried in parallel for latency.  Each backend
    degrades gracefully — if one is unavailable the others still return
    results.
    """

    def __init__(
        self,
        trade_reflector: TradeReflector | None = None,
        memory_client: TradingMemoryClient | None = None,
        prompt_store: PromptStore | None = None,
    ) -> None:
        self._reflector = trade_reflector
        self._client = memory_client
        self._pstore = prompt_store

    async def remember(
        self,
        agent_name: str,
        query: str,
        agent_config: AgentConfig | None = None,
        *,
        top_k: int = 5,
        include_identity: bool = True,
        include_rules: bool = True,
    ) -> MemoryContext:
        """Query all memory backends in parallel and compose context.

        Args:
            agent_name: Agent to retrieve memories for.
            query: Natural-language query for relevance search.
            agent_config: Agent config (needed for identity generation).
            top_k: Max memories per backend.
            include_identity: Whether to include L0/L1 identity context.
            include_rules: Whether to include learned rules.

        Returns:
            MemoryContext with composed sections.
        """
        tasks: dict[str, Any] = {}

        if include_identity and self._pstore and agent_config:
            tasks["identity"] = self._get_identity(agent_name, agent_config)
        if include_rules and self._pstore:
            tasks["rules"] = self._get_rules(agent_name)
        if self._reflector:
            tasks["trade_memories"] = self._get_trade_memories(agent_name, query, top_k)
        if self._client:
            tasks["shared_observations"] = self._get_shared_observations(query, top_k)
            tasks["lessons"] = self._get_recent_lessons(agent_name)

        results: dict[str, Any] = {}
        if tasks:
            keys = list(tasks.keys())
            values = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for k, v in zip(keys, values):
                if isinstance(v, Exception):
                    logger.warning("Memory backend %s failed: %s", k, v)
                    results[k] = ""
                else:
                    results[k] = v
        return MemoryContext(
            identity=results.get("identity", ""),
            rules=results.get("rules", ""),
            lessons=results.get("lessons", ""),
            trade_memories=results.get("trade_memories", ""),
            shared_observations=results.get("shared_observations", ""),
        )

    # --- Private helpers (one per backend) ---

    async def _get_identity(self, agent_name: str, agent_config: Any) -> str:
        try:
            ctx = self._pstore.get_agent_context(agent_name)
            if ctx:
                return ctx
            await self._pstore.generate_agent_context(
                agent_name=agent_name,
                agent_config=agent_config,
            )
            ctx = self._pstore.get_agent_context(agent_name)
            return ctx or ""
        except Exception as e:
            logger.warning("Identity generation failed for %s: %s", agent_name, e)
            return ""

    async def _get_rules(self, agent_name: str) -> str:
        try:
            rules = self._pstore.get_runtime_prompt(agent_name)
            return rules or ""
        except Exception as e:
            logger.warning("Rules retrieval failed for %s: %s", agent_name, e)
            return ""

    async def _get_trade_memories(self, agent_name: str, query: str, top_k: int) -> str:
        try:
            memories = await self._reflector.query(
                symbol=agent_name, context=query, agent_name=agent_name, top_k=top_k
            )
            if not memories:
                return ""
            lines = []
            for m in memories[:top_k]:
                content = m.get("value", m.get("content", str(m)))
                lines.append(f"- {content[:200]}")
            return "## Trade Memories\n" + "\n".join(lines)
        except Exception as e:
            logger.warning("Trade memory query failed for %s: %s", agent_name, e)
            return ""

    async def _get_shared_observations(self, query: str, top_k: int) -> str:
        try:
            results = await self._client.search_both(query=query, top_k=top_k)
            if not results:
                return ""
            lines = []
            for r in results[:top_k]:
                content = r.get("value", r.get("content", str(r)))
                lines.append(f"- {content[:200]}")
            return "## Shared Market Observations\n" + "\n".join(lines)
        except Exception as e:
            logger.warning("Shared memory query failed: %s", e)
            return ""

    async def _get_recent_lessons(self, agent_name: str) -> str:
        try:
            await self._pstore.load(agent_name, recent_lessons_window=5)
            prompt = self._pstore.get_runtime_prompt(agent_name)
            if not prompt:
                return ""
            lessons_section = ""
            if "## Recent Lessons" in prompt:
                start = prompt.index("## Recent Lessons")
                lessons_section = prompt[start:]
            return lessons_section
        except Exception as e:
            logger.warning("Lessons retrieval failed for %s: %s", agent_name, e)
            return ""

    async def store_observation(
        self,
        content: str,
        tags: list[str] | None = None,
        *,
        shared: bool = False,
    ) -> dict:
        if not self._client:
            logger.warning("No memory client available for store_observation")
            return {}
        if shared:
            return await self._client.store_shared(content=content, tags=tags)
        return await self._client.store_private(content=content, tags=tags)

    async def reflect_trade(
        self,
        trade: Any,
        agent_name: str,
    ) -> None:
        if not self._reflector:
            logger.warning("No trade reflector available for reflect_trade")
            return
        await self._reflector.reflect(trade=trade, agent_name=agent_name)
