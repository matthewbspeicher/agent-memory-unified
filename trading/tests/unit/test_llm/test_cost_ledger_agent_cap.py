"""Per-agent daily LLM budget cap."""
from __future__ import annotations

import pytest

from llm.cost_ledger import CostLedger, LLMCostConfig


@pytest.mark.asyncio
async def test_agent_under_cap_returns_ok():
    ledger = CostLedger(redis=None, config=LLMCostConfig(daily_budget_cents=10000))
    ledger._local["alpha"] = 50.0
    assert await ledger.check_agent_budget("alpha", cap_cents=100) is True


@pytest.mark.asyncio
async def test_agent_at_cap_returns_not_ok():
    ledger = CostLedger(redis=None, config=LLMCostConfig(daily_budget_cents=10000))
    ledger._local["alpha"] = 100.0
    assert await ledger.check_agent_budget("alpha", cap_cents=100) is False


@pytest.mark.asyncio
async def test_agent_over_cap_returns_not_ok():
    ledger = CostLedger(redis=None, config=LLMCostConfig(daily_budget_cents=10000))
    ledger._local["alpha"] = 250.0
    assert await ledger.check_agent_budget("alpha", cap_cents=100) is False


@pytest.mark.asyncio
async def test_agent_without_cap_is_always_ok():
    ledger = CostLedger(redis=None, config=LLMCostConfig(daily_budget_cents=10000))
    ledger._local["alpha"] = 99999.0
    assert await ledger.check_agent_budget("alpha", cap_cents=None) is True


@pytest.mark.asyncio
async def test_for_agent_is_over_budget_hook(monkeypatch):
    """for_agent() scopes the cap; is_over_budget() is the hook call-sites use."""
    from llm.client import LLMClient

    ledger = CostLedger(redis=None, config=LLMCostConfig(daily_budget_cents=10000))
    ledger._local["capped_agent"] = 200.0
    ledger._local["under_agent"] = 10.0

    parent = object.__new__(LLMClient)
    parent._chain = []
    parent._agent_name = None
    parent._cost_ledger = ledger
    parent._notifier = None
    parent._fired_alerts = set()
    parent.registry = None
    parent._fail_counts = {}
    parent._disabled = {}
    parent._max_fails = 5
    parent._agent_budgets = {"capped_agent": 100, "under_agent": 100}

    capped = parent.for_agent("capped_agent")
    under = parent.for_agent("under_agent")
    unknown = parent.for_agent("no_cap_agent")

    assert await capped.is_over_budget() is True
    assert await under.is_over_budget() is False
    # Agent with no entry in agent_budgets has no per-agent cap → never over.
    assert await unknown.is_over_budget() is False
