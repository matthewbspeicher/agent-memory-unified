"""
Redis-backed LLM cost tracker with in-memory fallback.

Tracks spend per rolling 24h window using Redis INCRBYFLOAT for atomicity.
Falls back to in-memory dict when Redis is unavailable (fail-open).

Usage:
    from llm.cost_ledger import CostLedger

    ledger = CostLedger(redis=redis_client, config=llm_config)
    cost = await ledger.record("react_analyst", "anthropic", "claude-haiku-4-5-20251001", 1000, 500)
    event = await ledger.check_thresholds()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

DEFAULT_COST_TABLE: dict[str, dict[str, dict[str, float]]] = {
    "anthropic": {
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
        "*": {"input": 0.80, "output": 4.00},
    },
    "bedrock": {
        "*": {"input": 0.25, "output": 1.25},
    },
    "groq": {
        "*": {"input": 0.0, "output": 0.0},
    },
    "ollama": {
        "*": {"input": 0.0, "output": 0.0},
    },
    "rule-based": {
        "*": {"input": 0.0, "output": 0.0},
    },
}

_KEY_GLOBAL = "llm:cost:global"
_KEY_AGENT = "llm:cost:agent:{name}"
_KEY_GRACE = "llm:cost:grace_deadline"
_TTL_24H = 86400


@dataclass
class LLMCostConfig:
    """Cost-control configuration for CostLedger.

    Mirrors the fields added to LLMConfig in config.py. Kept separate so
    CostLedger can be imported without pulling in the full config module.
    """

    daily_budget_cents: int = 500
    warning_threshold_pct: float = 0.80
    grace_period_minutes: int = 15
    cost_table_override: str | None = None


class CostLedger:
    """Redis-backed LLM cost tracker with in-memory fallback.

    All monetary values are in **cents** (float). The 24h window is
    implemented via Redis TTL — no cron required.
    """

    def __init__(self, redis: "Redis | None", config: LLMCostConfig) -> None:
        self._redis = redis
        self._config = config
        self._local: dict[str, float] = {}
        self._cost_table = self._merge_cost_table(
            DEFAULT_COST_TABLE, config.cost_table_override
        )
        self._free_providers: set[str] = self._derive_free_providers(self._cost_table)

    async def record(
        self,
        agent_name: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Record LLM usage atomically. Returns cost in cents.

        Uses Redis INCRBYFLOAT pipeline for atomicity. Falls back to
        in-memory dict when Redis is unavailable.
        """
        cost = self._calculate_cost(provider, model, input_tokens, output_tokens)
        if cost == 0.0:
            return 0.0

        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.incrbyfloat(_KEY_GLOBAL, cost)
                pipe.incrbyfloat(_KEY_AGENT.format(name=agent_name), cost)
                await pipe.execute()

                for key in (_KEY_GLOBAL, _KEY_AGENT.format(name=agent_name)):
                    if await self._redis.ttl(key) == -1:
                        await self._redis.expire(key, _TTL_24H)

                await self._maybe_set_grace_deadline(
                    await self.get_global_spend(), self._config.daily_budget_cents
                )
            except Exception:
                logger.warning(
                    "CostLedger: Redis error during record(); falling back to in-memory",
                    exc_info=True,
                )
                self._local["global"] = self._local.get("global", 0.0) + cost
                self._local[agent_name] = self._local.get(agent_name, 0.0) + cost
        else:
            self._local["global"] = self._local.get("global", 0.0) + cost
            self._local[agent_name] = self._local.get(agent_name, 0.0) + cost

        return cost

    async def get_global_spend(self) -> float:
        """Total spend in current 24h window (cents)."""
        if self._redis is not None:
            try:
                raw = await self._redis.get(_KEY_GLOBAL)
                return float(raw) if raw is not None else 0.0
            except Exception:
                logger.warning("CostLedger: Redis error in get_global_spend()")
        return self._local.get("global", 0.0)

    async def get_agent_spend(self, agent_name: str) -> float:
        """Per-agent spend in current 24h window (cents)."""
        if self._redis is not None:
            try:
                raw = await self._redis.get(_KEY_AGENT.format(name=agent_name))
                return float(raw) if raw is not None else 0.0
            except Exception:
                logger.warning("CostLedger: Redis error in get_agent_spend()")
        return self._local.get(agent_name, 0.0)

    async def check_agent_budget(
        self, agent_name: str, cap_cents: int | None
    ) -> bool:
        """True when the agent may still spend more LLM dollars today.

        ``cap_cents=None`` disables the per-agent cap (global budget still
        applies separately via ``check_thresholds``).
        """
        if cap_cents is None:
            return True
        spent = await self.get_agent_spend(agent_name)
        return spent < cap_cents

    def get_cost(self, provider: str, model: str) -> dict[str, float]:
        """Look up per-1M-token cost for a provider/model pair.

        Lookup order: exact model → wildcard "*" → safe default (0, 0).
        """
        provider_table = self._cost_table.get(provider, {})
        rates = provider_table.get(model) or provider_table.get("*")
        if rates is None:
            return {"input": 0.0, "output": 0.0}
        return dict(rates)

    async def get_breakdown(self) -> tuple[str, float, dict[str, float]]:
        """Returns (top_agent_name, top_agent_spend_cents, provider_spend_dict).

        Scans llm:cost:agent:* keys for the top-spending agent.
        provider_spend_dict is empty in v1 (no per-provider tracking yet).
        """
        if self._redis is None:
            agents = {k: v for k, v in self._local.items() if k != "global"}
            if not agents:
                return "unknown", 0.0, {}
            top_agent = max(agents, key=lambda k: agents[k])
            return top_agent, agents[top_agent], {}

        top_agent, top_spend = "unknown", 0.0
        try:
            cursor: int = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor, match="llm:cost:agent:*", count=100
                )
                for key in keys:
                    raw = await self._redis.get(key)
                    val = float(raw) if raw is not None else 0.0
                    agent = key.decode() if isinstance(key, bytes) else key
                    agent = agent.split(":")[-1]
                    if val > top_spend:
                        top_agent, top_spend = agent, val
                if cursor == 0:
                    break
        except Exception:
            logger.warning("CostLedger: Redis error in get_breakdown()")

        return top_agent, top_spend, {}

    async def should_block_paid(self) -> bool:
        """True if paid providers should be filtered from the chain.

        Returns False during the grace period (allows in-flight work to finish).
        """
        spend = await self.get_global_spend()
        budget = self._config.daily_budget_cents
        if budget <= 0 or spend < budget:
            return False

        deadline = await self._get_grace_deadline()
        if deadline is None:
            return False

        return datetime.now(timezone.utc) > deadline

    async def check_thresholds(self) -> str | None:
        """Returns event type if a threshold was crossed, None otherwise.

        Event types:
          - "cost.warning"      — 80% of daily budget
          - "cost.ceiling_hit"  — 100%+, grace period active
          - "cost.paid_blocked" — 100%+, grace period expired
        """
        spend = await self.get_global_spend()
        budget = self._config.daily_budget_cents
        if budget <= 0:
            return None

        pct = spend / budget

        if pct < self._config.warning_threshold_pct:
            return None

        if pct >= 1.0:
            await self._maybe_set_grace_deadline(spend, budget)
            deadline = await self._get_grace_deadline()
            if deadline and datetime.now(timezone.utc) > deadline:
                return "cost.paid_blocked"
            return "cost.ceiling_hit"

        return "cost.warning"

    async def _maybe_set_grace_deadline(self, spend: float, budget: float) -> None:
        """Set grace deadline when ceiling is first hit (idempotent).

        Uses Redis TTL check to avoid overwriting an existing deadline.
        """
        if spend < budget:
            return
        if self._redis is None:
            return

        try:
            ttl = await self._redis.ttl(_KEY_GRACE)
            if ttl == -1 or ttl > 0:
                return
            deadline = datetime.now(timezone.utc) + timedelta(
                minutes=self._config.grace_period_minutes
            )
            await self._redis.setex(_KEY_GRACE, _TTL_24H, deadline.isoformat())
        except Exception:
            logger.warning("CostLedger: Redis error in _maybe_set_grace_deadline()")

    async def _get_grace_deadline(self) -> datetime | None:
        """Returns grace deadline datetime, or None if not set."""
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(_KEY_GRACE)
            if raw is None:
                return None
            raw_str = raw.decode() if isinstance(raw, bytes) else raw
            return datetime.fromisoformat(raw_str)
        except Exception:
            logger.warning("CostLedger: Redis error in _get_grace_deadline()")
            return None

    def _calculate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Calculate cost in cents for a single LLM call.

        Rates are per 1M tokens; tokens are divided by 1_000_000.
        """
        rates = self.get_cost(provider, model)
        cost = (input_tokens / 1_000_000) * rates["input"] + (
            output_tokens / 1_000_000
        ) * rates["output"]
        return cost

    @staticmethod
    def _derive_free_providers(
        cost_table: dict[str, dict[str, dict[str, float]]],
    ) -> set[str]:
        """Derive the set of providers where all model rates are zero."""
        return {
            name
            for name, models in cost_table.items()
            if all(
                p.get("input", 0.0) == 0.0 and p.get("output", 0.0) == 0.0
                for p in models.values()
            )
        }

    @staticmethod
    def _merge_cost_table(
        base: dict[str, dict[str, dict[str, float]]],
        override_json: str | None,
    ) -> dict[str, dict[str, dict[str, float]]]:
        """Deep-merge DEFAULT_COST_TABLE with an optional JSON override.

        The override is a JSON string with the same nested structure.
        Provider-level keys are merged; model-level keys are replaced.
        Unknown/malformed override JSON is logged and ignored.
        """
        import copy

        merged = copy.deepcopy(base)
        if not override_json:
            return merged

        try:
            override = json.loads(override_json)
        except json.JSONDecodeError:
            logger.warning(
                "CostLedger: invalid cost_table_override JSON — using defaults"
            )
            return merged

        if not isinstance(override, dict):
            logger.warning(
                "CostLedger: cost_table_override must be a JSON object — using defaults"
            )
            return merged

        for provider, models in override.items():
            if not isinstance(models, dict):
                continue
            if provider not in merged:
                merged[provider] = {}
            for model, rates in models.items():
                if isinstance(rates, dict):
                    merged[provider][model] = rates

        return merged
