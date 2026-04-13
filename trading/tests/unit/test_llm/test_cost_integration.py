import pytest
from unittest.mock import AsyncMock

from llm.client import LLMClient
from llm.cost_ledger import CostLedger, LLMCostConfig


@pytest.fixture
def cost_config():
    return LLMCostConfig(
        daily_budget_cents=100, warning_threshold_pct=0.80, grace_period_minutes=1
    )


@pytest.fixture
def ledger_no_redis(cost_config):
    return CostLedger(redis=None, config=cost_config)


class TestChainFiltering:
    @pytest.mark.asyncio
    async def test_all_providers_under_budget(self, ledger_no_redis):
        client = LLMClient(
            anthropic_key="sk-test",
            groq_key="gsk-test",
            cost_ledger=ledger_no_redis,
        )
        chain = await client._resolve_chain()
        assert "anthropic" in chain
        assert "groq" in chain

    @pytest.mark.asyncio
    async def test_only_free_providers_over_budget(self, ledger_no_redis):
        ledger_no_redis._local["global"] = 150.0
        client = LLMClient(
            anthropic_key="sk-test",
            groq_key="gsk-test",
            cost_ledger=ledger_no_redis,
        )

        async def mock_should_block():
            return True

        ledger_no_redis.should_block_paid = mock_should_block

        chain = await client._resolve_chain()
        assert "groq" in chain
        assert "ollama" in chain
        assert "rule-based" in chain


class TestNoCostLedger:
    @pytest.mark.asyncio
    async def test_works_without_cost_ledger(self):
        client = LLMClient(anthropic_key="sk-test")
        chain = await client._resolve_chain()
        assert "anthropic" in chain
