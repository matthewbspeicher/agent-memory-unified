import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from llm.cost_ledger import CostLedger, LLMCostConfig, DEFAULT_COST_TABLE


@pytest.fixture
def cost_config():
    return LLMCostConfig(
        daily_budget_cents=500,
        warning_threshold_pct=0.80,
        grace_period_minutes=15,
        cost_table_override=None,
    )


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.ttl = AsyncMock(return_value=-1)
    redis.pipeline = MagicMock()
    pipe = AsyncMock()
    pipe.incrbyfloat = MagicMock()
    pipe.execute = AsyncMock()
    redis.pipeline.return_value = pipe
    redis.scan = AsyncMock(return_value=(0, []))
    return redis


@pytest.fixture
def ledger_no_redis(cost_config):
    return CostLedger(redis=None, config=cost_config)


@pytest.fixture
def ledger_with_redis(cost_config, mock_redis):
    return CostLedger(redis=mock_redis, config=cost_config)


class TestCostCalculation:
    def test_calculate_cost_anthropic(self, ledger_no_redis):
        cost = ledger_no_redis._calculate_cost(
            "anthropic", "claude-haiku-4-5-20251001", 1_000_000, 1_000_000
        )
        assert cost == 4.80

    def test_calculate_cost_free_provider(self, ledger_no_redis):
        cost = ledger_no_redis._calculate_cost(
            "groq", "llama-3.3-70b-versatile", 1_000_000, 1_000_000
        )
        assert cost == 0.0

    def test_calculate_cost_unknown_provider(self, ledger_no_redis):
        cost = ledger_no_redis._calculate_cost("unknown", "model", 1000, 1000)
        assert cost == 0.0

    def test_calculate_cost_fractional_tokens(self, ledger_no_redis):
        cost = ledger_no_redis._calculate_cost("anthropic", "*", 1000, 500)
        assert cost == pytest.approx(0.0008 + 0.002, rel=1e-4)


class TestGetCost:
    def test_exact_model_match(self, ledger_no_redis):
        rates = ledger_no_redis.get_cost("anthropic", "claude-haiku-4-5-20251001")
        assert rates == {"input": 0.80, "output": 4.00}

    def test_wildcard_fallback(self, ledger_no_redis):
        rates = ledger_no_redis.get_cost("anthropic", "unknown-model")
        assert rates == {"input": 0.80, "output": 4.00}

    def test_unknown_provider_returns_zeros(self, ledger_no_redis):
        rates = ledger_no_redis.get_cost("unknown", "model")
        assert rates == {"input": 0.0, "output": 0.0}


class TestFreeProviders:
    def test_derive_free_providers(self, ledger_no_redis):
        assert "groq" in ledger_no_redis._free_providers
        assert "ollama" in ledger_no_redis._free_providers
        assert "rule-based" in ledger_no_redis._free_providers
        assert "anthropic" not in ledger_no_redis._free_providers
        assert "bedrock" not in ledger_no_redis._free_providers


class TestRecordInMemory:
    @pytest.mark.asyncio
    async def test_record_increments_global(self, ledger_no_redis):
        await ledger_no_redis.record("test-agent", "anthropic", "*", 1000000, 1000000)
        assert ledger_no_redis._local["global"] == 4.80

    @pytest.mark.asyncio
    async def test_record_increments_agent(self, ledger_no_redis):
        await ledger_no_redis.record("test-agent", "anthropic", "*", 1000000, 1000000)
        assert ledger_no_redis._local["test-agent"] == 4.80

    @pytest.mark.asyncio
    async def test_record_zero_tokens_returns_zero(self, ledger_no_redis):
        cost = await ledger_no_redis.record("test-agent", "groq", "*", 0, 0)
        assert cost == 0.0


class TestRecordRedis:
    @pytest.mark.asyncio
    async def test_record_uses_pipeline(self, ledger_with_redis, mock_redis):
        await ledger_with_redis.record("test-agent", "anthropic", "*", 1000000, 1000000)
        mock_redis.pipeline.return_value.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_falls_back_on_redis_error(
        self, ledger_with_redis, mock_redis
    ):
        mock_redis.pipeline.side_effect = Exception("Redis down")
        cost = await ledger_with_redis.record(
            "test-agent", "anthropic", "*", 1000000, 1000000
        )
        assert cost == 4.80
        assert ledger_with_redis._local["global"] == 4.80


class TestGetSpend:
    @pytest.mark.asyncio
    async def test_get_global_spend_in_memory(self, ledger_no_redis):
        ledger_no_redis._local["global"] = 100.0
        assert await ledger_no_redis.get_global_spend() == 100.0

    @pytest.mark.asyncio
    async def test_get_agent_spend_in_memory(self, ledger_no_redis):
        ledger_no_redis._local["my-agent"] = 50.0
        assert await ledger_no_redis.get_agent_spend("my-agent") == 50.0

    @pytest.mark.asyncio
    async def test_get_agent_spend_unknown_returns_zero(self, ledger_no_redis):
        assert await ledger_no_redis.get_agent_spend("unknown") == 0.0


class TestShouldBlockPaid:
    @pytest.mark.asyncio
    async def test_under_budget_returns_false(self, ledger_no_redis):
        ledger_no_redis._local["global"] = 100.0
        assert await ledger_no_redis.should_block_paid() is False

    @pytest.mark.asyncio
    async def test_over_budget_no_grace_returns_false(self, ledger_no_redis):
        ledger_no_redis._local["global"] = 600.0
        assert await ledger_no_redis.should_block_paid() is False

    @pytest.mark.asyncio
    async def test_over_budget_grace_expired_returns_true(self, ledger_no_redis):
        ledger_no_redis._local["global"] = 600.0
        ledger_no_redis._get_grace_deadline = AsyncMock(
            return_value=datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        assert await ledger_no_redis.should_block_paid() is True


class TestCheckThresholds:
    @pytest.mark.asyncio
    async def test_under_warning_returns_none(self, ledger_no_redis):
        ledger_no_redis._local["global"] = 300.0
        assert await ledger_no_redis.check_thresholds() is None

    @pytest.mark.asyncio
    async def test_warning_returns_warning(self, ledger_no_redis):
        ledger_no_redis._local["global"] = 450.0
        assert await ledger_no_redis.check_thresholds() == "cost.warning"

    @pytest.mark.asyncio
    async def test_ceiling_in_grace_returns_ceiling_hit(self, ledger_no_redis):
        ledger_no_redis._local["global"] = 600.0
        ledger_no_redis._get_grace_deadline = AsyncMock(
            return_value=datetime.now(timezone.utc) + timedelta(minutes=5)
        )
        assert await ledger_no_redis.check_thresholds() == "cost.ceiling_hit"

    @pytest.mark.asyncio
    async def test_ceiling_grace_expired_returns_blocked(self, ledger_no_redis):
        ledger_no_redis._local["global"] = 600.0
        ledger_no_redis._get_grace_deadline = AsyncMock(
            return_value=datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        assert await ledger_no_redis.check_thresholds() == "cost.paid_blocked"


class TestMergeCostTable:
    def test_no_override_returns_default(self, cost_config):
        ledger = CostLedger(redis=None, config=cost_config)
        assert "anthropic" in ledger._cost_table

    def test_override_merges_correctly(self, cost_config):
        cost_config.cost_table_override = (
            '{"anthropic": {"*": {"input": 1.0, "output": 5.0}}}'
        )
        ledger = CostLedger(redis=None, config=cost_config)
        assert ledger._cost_table["anthropic"]["*"] == {"input": 1.0, "output": 5.0}

    def test_invalid_json_ignored(self, cost_config):
        cost_config.cost_table_override = "not json"
        ledger = CostLedger(redis=None, config=cost_config)
        assert ledger._cost_table == DEFAULT_COST_TABLE


class TestGetBreakdown:
    @pytest.mark.asyncio
    async def test_breakdown_in_memory(self, ledger_no_redis):
        ledger_no_redis._local["agent-a"] = 100.0
        ledger_no_redis._local["agent-b"] = 200.0
        top_agent, top_spend, _ = await ledger_no_redis.get_breakdown()
        assert top_agent == "agent-b"
        assert top_spend == 200.0

    @pytest.mark.asyncio
    async def test_breakdown_empty_returns_unknown(self, ledger_no_redis):
        top_agent, top_spend, _ = await ledger_no_redis.get_breakdown()
        assert top_agent == "unknown"
        assert top_spend == 0.0
