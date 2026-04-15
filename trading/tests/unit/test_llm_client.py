"""
Unit tests for the unified LLMClient fallback chain.

All provider calls are mocked — no API keys required.
Tests cover: fallback ordering, circuit breaker, rule-based scoring,
structured parsing (score_headline, estimate_probability), and chat().
"""

import pytest
from unittest.mock import AsyncMock, patch

from llm.client import (
    LLMClient,
    LLMResult,
    ScoredHeadline,
    ProbabilityEstimate,
    _rule_based_score_headline,
    _rule_based_probability,
)


# ---------------------------------------------------------------------------
# Rule-based fallback tests (zero-cost, always available)
# ---------------------------------------------------------------------------


class TestRuleBasedScoreHeadline:
    def test_bullish_headline(self):
        result = _rule_based_score_headline("Stock surges on record earnings growth")
        assert result.sentiment == "bullish_yes"
        assert result.mispricing_score > 0
        assert result.relevance > 0.3

    def test_bearish_headline(self):
        result = _rule_based_score_headline("Company faces lawsuit and bankruptcy risk")
        assert result.sentiment == "bearish_yes"
        assert result.mispricing_score < 0
        assert result.relevance > 0.3

    def test_neutral_headline(self):
        result = _rule_based_score_headline("Weather is nice today")
        assert result.sentiment == "neutral"
        assert result.mispricing_score == 0.0
        assert result.relevance == 0.3

    def test_mixed_headline(self):
        result = _rule_based_score_headline("Growth slows but profit beats estimates")
        assert isinstance(result, ScoredHeadline)
        assert 0 <= result.relevance <= 1.0
        assert result.sentiment in ("bullish_yes", "bearish_yes", "neutral")


class TestRuleBasedProbability:
    def test_basic_overlap(self):
        result = _rule_based_probability(
            "Will inflation rise?",
            ["Inflation data shows increase", "CPI numbers up sharply"],
        )
        assert isinstance(result, ProbabilityEstimate)
        assert 0.01 <= result.implied_probability <= 0.99
        assert 0 <= result.confidence <= 100
        assert "overlap" in result.reasoning.lower()

    def test_no_headlines(self):
        result = _rule_based_probability("Will X happen?", [])
        assert result.implied_probability == 0.5
        assert result.confidence >= 0

    def test_negation_inverts(self):
        result_pos = _rule_based_probability(
            "Will prices rise?", ["prices rise sharply"]
        )
        result_neg = _rule_based_probability(
            "Will prices not rise?", ["prices rise sharply"]
        )
        # Negation should push probability in opposite direction
        assert result_neg.implied_probability != result_pos.implied_probability


# ---------------------------------------------------------------------------
# Circuit breaker tests
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_provider_disabled_after_max_failures(self):
        client = LLMClient(chain=["anthropic", "rule-based"])
        for _ in range(5):
            client._record_failure("anthropic")
        assert client._is_disabled("anthropic") is True

    def test_provider_not_disabled_before_threshold(self):
        client = LLMClient(chain=["anthropic", "rule-based"])
        for _ in range(4):
            client._record_failure("anthropic")
        assert client._is_disabled("anthropic") is False

    def test_success_resets_failure_count(self):
        client = LLMClient(chain=["anthropic", "rule-based"])
        for _ in range(4):
            client._record_failure("anthropic")
        client._record_success("anthropic")
        assert client._fail_counts["anthropic"] == 0
        assert client._is_disabled("anthropic") is False

    def test_re_enable_all(self):
        client = LLMClient(chain=["anthropic", "groq", "rule-based"])
        for _ in range(5):
            client._record_failure("anthropic")
            client._record_failure("groq")
        assert client._is_disabled("anthropic")
        assert client._is_disabled("groq")
        client.re_enable_all()
        assert not client._is_disabled("anthropic")
        assert not client._is_disabled("groq")


# ---------------------------------------------------------------------------
# Chain resolution tests
# ---------------------------------------------------------------------------


class TestChainResolution:
    @pytest.mark.asyncio
    async def test_removes_providers_without_keys(self):
        client = LLMClient(
            anthropic_key=None,
            groq_key=None,
            chain=["anthropic", "groq", "ollama", "rule-based"],
        )
        chain = await client._resolve_chain()
        assert "anthropic" not in chain
        assert "groq" not in chain
        assert "ollama" in chain
        assert "rule-based" in chain

    @pytest.mark.asyncio
    async def test_keeps_providers_with_keys(self):
        client = LLMClient(
            anthropic_key="sk-test",
            groq_key="gsk-test",
            chain=["anthropic", "groq", "ollama", "rule-based"],
        )
        chain = await client._resolve_chain()
        assert chain == ["anthropic", "groq", "ollama", "rule-based"]

    @pytest.mark.asyncio
    async def test_custom_chain_order(self):
        client = LLMClient(
            groq_key="gsk-test",
            chain=["groq", "ollama", "rule-based"],
        )
        chain = await client._resolve_chain()
        assert chain[0] == "groq"


# ---------------------------------------------------------------------------
# complete() fallback tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_uses_first_available_provider():
    """First provider succeeds — no fallback needed."""
    mock_result = LLMResult(
        text="test response", provider="groq", model="llama-3.3-70b-versatile"
    )

    client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
    # Mock the GroqProvider's complete method
    with patch.object(
        client.registry.get("groq"),
        "complete",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await client.complete("test prompt")

    assert result.text == "test response"
    assert result.provider == "groq"


@pytest.mark.asyncio
async def test_complete_falls_back_on_provider_failure():
    """First provider fails, second succeeds."""
    mock_result = LLMResult(
        text="ollama response", provider="ollama", model="llama3.2:3b"
    )

    client = LLMClient(groq_key="gsk-test", chain=["groq", "ollama", "rule-based"])
    # Mock groq to fail, ollama to succeed
    with patch.object(
        client.registry.get("groq"),
        "complete",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with patch.object(
            client.registry.get("ollama"),
            "complete",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await client.complete("test prompt")

    assert result.text == "ollama response"
    assert result.provider == "ollama"


@pytest.mark.asyncio
async def test_complete_records_failures():
    """Failed provider gets failure recorded."""
    client = LLMClient(groq_key="gsk-test", chain=["groq", "ollama", "rule-based"])
    with patch.object(
        client.registry.get("groq"),
        "complete",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with patch.object(
            client.registry.get("ollama"),
            "complete",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await client.complete("test prompt")

    assert client._fail_counts.get("groq", 0) == 1
    assert client._fail_counts.get("ollama", 0) == 1


@pytest.mark.asyncio
async def test_complete_skips_disabled_providers():
    """Disabled provider is skipped, next one is tried."""
    mock_result = LLMResult(
        text="ollama response", provider="ollama", model="llama3.2:3b"
    )

    client = LLMClient(groq_key="gsk-test", chain=["groq", "ollama", "rule-based"])
    # Disable groq via circuit breaker
    for _ in range(5):
        client._record_failure("groq")

    mock_groq = AsyncMock(return_value=None)
    with patch.object(client.registry.get("groq"), "complete", mock_groq):
        with patch.object(
            client.registry.get("ollama"),
            "complete",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await client.complete("test prompt")

    mock_groq.assert_not_called()
    assert result.provider == "ollama"


# ---------------------------------------------------------------------------
# chat() fallback tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_uses_first_available():
    mock_result = LLMResult(
        text="chat response", provider="groq", model="llama-3.3-70b-versatile"
    )

    client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
    with patch.object(
        client.registry.get("groq"),
        "chat",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await client.chat(
            "You are helpful.", [{"role": "user", "content": "Hi"}]
        )

    assert result.text == "chat response"
    assert result.provider == "groq"


@pytest.mark.asyncio
async def test_chat_skips_rule_based():
    """Chat has no rule-based fallback — returns error message instead."""
    client = LLMClient(chain=["ollama", "rule-based"])
    with patch.object(
        client.registry.get("ollama"), "chat", new_callable=AsyncMock, return_value=None
    ):
        result = await client.chat(
            "You are helpful.", [{"role": "user", "content": "Hello"}]
        )

    assert result.provider == "rule-based"
    assert "unable" in result.text.lower() or "command" in result.text.lower()


# ---------------------------------------------------------------------------
# score_headline() structured output tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_headline_parses_llm_json():
    """Valid LLM JSON response is parsed into ScoredHeadline."""
    mock_result = LLMResult(
        text='{"relevance": 0.85, "sentiment": "bullish_yes", "mispricing_score": 0.4}',
        provider="groq",
        model="llama-3.3-70b-versatile",
    )

    client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
    with patch.object(
        client.registry.get("groq"),
        "complete",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await client.score_headline(
            "Will AAPL rise?", "Apple reports record Q4"
        )

    assert isinstance(result, ScoredHeadline)
    assert result.relevance == 0.85
    assert result.sentiment == "bullish_yes"
    assert result.mispricing_score == 0.4


@pytest.mark.asyncio
async def test_score_headline_clamps_values():
    """Out-of-range values are clamped to valid bounds."""
    mock_result = LLMResult(
        text='{"relevance": 2.5, "sentiment": "bullish_yes", "mispricing_score": -3.0}',
        provider="groq",
        model="test",
    )

    client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
    with patch.object(
        client.registry.get("groq"),
        "complete",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await client.score_headline("Test", "Test headline")

    assert result.relevance == 1.0  # clamped from 2.5
    assert result.mispricing_score == -1.0  # clamped from -3.0


@pytest.mark.asyncio
async def test_score_headline_falls_back_to_rules_on_bad_json():
    """Unparseable LLM output triggers rule-based fallback."""
    mock_result = LLMResult(
        text="Sorry, I cannot parse that.", provider="groq", model="test"
    )

    client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
    with patch.object(
        client.registry.get("groq"),
        "complete",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await client.score_headline("Test contract", "Stocks surge on growth")

    assert isinstance(result, ScoredHeadline)
    # Rule-based should detect "surge" and "growth"
    assert result.sentiment == "bullish_yes"


@pytest.mark.asyncio
async def test_score_headline_all_providers_fail_uses_rules():
    """All providers fail — rule-based always works."""
    client = LLMClient(chain=["rule-based"])
    result = await client.score_headline(
        "Will oil prices drop?", "Oil prices plunge on oversupply"
    )

    assert isinstance(result, ScoredHeadline)
    assert result.sentiment == "bearish_yes"


# ---------------------------------------------------------------------------
# estimate_probability() structured output tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_probability_parses_llm_json():
    mock_result = LLMResult(
        text='{"implied_probability": 0.72, "confidence": 80, "reasoning": "Strong signal"}',
        provider="ollama",
        model="llama3.2:3b",
    )

    client = LLMClient(chain=["ollama", "rule-based"])
    with patch.object(
        client.registry.get("ollama"),
        "complete",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await client.estimate_probability(
            "Will X happen?", ["X is very likely"]
        )

    assert isinstance(result, ProbabilityEstimate)
    assert result.implied_probability == 0.72
    assert result.confidence == 80


@pytest.mark.asyncio
async def test_estimate_probability_clamps_bounds():
    mock_result = LLMResult(
        text='{"implied_probability": 1.5, "confidence": 200, "reasoning": "test"}',
        provider="groq",
        model="test",
    )

    client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
    with patch.object(
        client.registry.get("groq"),
        "complete",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await client.estimate_probability("Test?", ["test"])

    assert result.implied_probability == 0.99  # clamped
    assert result.confidence == 100  # clamped


@pytest.mark.asyncio
async def test_estimate_probability_falls_back_to_rules():
    client = LLMClient(chain=["rule-based"])
    result = await client.estimate_probability(
        "Will inflation rise?", ["inflation rising fast"]
    )

    assert isinstance(result, ProbabilityEstimate)
    assert 0.01 <= result.implied_probability <= 0.99
    assert "overlap" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# Foresight-style ensemble aggregation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensemble_takes_median_of_three_samples():
    """N=3 samples with different probabilities → median of the three."""
    samples = [
        LLMResult(text='{"implied_probability": 0.30, "confidence": 70, "reasoning": "low-sample"}', provider="ollama", model="x"),
        LLMResult(text='{"implied_probability": 0.50, "confidence": 70, "reasoning": "mid-sample"}', provider="ollama", model="x"),
        LLMResult(text='{"implied_probability": 0.40, "confidence": 70, "reasoning": "high-sample"}', provider="ollama", model="x"),
    ]

    client = LLMClient(chain=["ollama", "rule-based"])
    with patch.object(
        client.registry.get("ollama"),
        "complete",
        new_callable=AsyncMock,
        side_effect=samples,
    ):
        result = await client.estimate_probability("Q?", ["h"])

    # Median of 0.30, 0.40, 0.50 = 0.40
    assert result.implied_probability == pytest.approx(0.40)
    # Spread = 0.20 → > 0.10 branch → -10 confidence penalty
    assert result.confidence == 60


@pytest.mark.asyncio
async def test_ensemble_spread_reduces_confidence():
    """High-spread samples trigger confidence penalty."""
    samples = [
        LLMResult(text='{"implied_probability": 0.10, "confidence": 80, "reasoning": "a"}', provider="ollama", model="x"),
        LLMResult(text='{"implied_probability": 0.50, "confidence": 80, "reasoning": "b"}', provider="ollama", model="x"),
        LLMResult(text='{"implied_probability": 0.90, "confidence": 80, "reasoning": "c"}', provider="ollama", model="x"),
    ]

    client = LLMClient(chain=["ollama", "rule-based"])
    with patch.object(
        client.registry.get("ollama"),
        "complete",
        new_callable=AsyncMock,
        side_effect=samples,
    ):
        result = await client.estimate_probability("Q?", ["h"])

    # Median of 0.10, 0.50, 0.90 = 0.50
    assert result.implied_probability == pytest.approx(0.50)
    # Spread = 0.80 > 0.20 → -25 confidence penalty
    assert result.confidence == 55


@pytest.mark.asyncio
async def test_ensemble_uses_partial_successes():
    """When only 2 of 3 samples parse, still return an estimate from the 2."""
    samples = [
        LLMResult(text="not json at all", provider="ollama", model="x"),
        LLMResult(text='{"implied_probability": 0.40, "confidence": 60, "reasoning": "ok"}', provider="ollama", model="x"),
        LLMResult(text='{"implied_probability": 0.60, "confidence": 60, "reasoning": "ok2"}', provider="ollama", model="x"),
    ]

    client = LLMClient(chain=["ollama", "rule-based"])
    with patch.object(
        client.registry.get("ollama"),
        "complete",
        new_callable=AsyncMock,
        side_effect=samples,
    ):
        result = await client.estimate_probability("Q?", ["h"])

    # Median of 0.40, 0.60 = 0.50
    assert result.implied_probability == pytest.approx(0.50)
    # Spread = 0.20 → > 0.10 branch → -10 confidence penalty
    assert result.confidence == 50


@pytest.mark.asyncio
async def test_ensemble_falls_through_when_all_samples_fail_to_parse():
    """Zero successful samples → next provider in chain (rule-based here)."""
    bad_results = [
        LLMResult(text="garbage 1", provider="ollama", model="x"),
        LLMResult(text="garbage 2", provider="ollama", model="x"),
        LLMResult(text="garbage 3", provider="ollama", model="x"),
    ]

    client = LLMClient(chain=["ollama", "rule-based"])
    with patch.object(
        client.registry.get("ollama"),
        "complete",
        new_callable=AsyncMock,
        side_effect=bad_results,
    ):
        result = await client.estimate_probability(
            "Will inflation rise?", ["inflation rising fast"]
        )

    # Fell through to rule-based — reasoning contains "overlap"
    assert "overlap" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_ensemble_n_equals_one_disables_ensemble():
    """ensemble_n=1 → single call, no median aggregation."""
    sample = LLMResult(
        text='{"implied_probability": 0.35, "confidence": 75, "reasoning": "single"}',
        provider="ollama",
        model="x",
    )

    client = LLMClient(chain=["ollama", "rule-based"])
    call_count = 0

    async def _counting_complete(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return sample

    with patch.object(
        client.registry.get("ollama"), "complete", side_effect=_counting_complete
    ):
        result = await client.estimate_probability("Q?", ["h"], ensemble_n=1)

    assert call_count == 1
    assert result.implied_probability == 0.35
    assert result.confidence == 75  # no spread penalty with only 1 sample


# ---------------------------------------------------------------------------
# Integration: full fallback chain simulation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_chain_anthropic_to_groq_to_rules():
    """Simulates Anthropic failing, Groq failing, falling back to rules."""
    client = LLMClient(
        anthropic_key="sk-test",
        groq_key="gsk-test",
        chain=["anthropic", "groq", "ollama", "rule-based"],
    )

    # Mock all providers to fail
    with patch.object(
        client.registry.get("anthropic"),
        "complete",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_a:
        with patch.object(
            client.registry.get("groq"),
            "complete",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_g:
            with patch.object(
                client.registry.get("ollama"),
                "complete",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_o:
                result = await client.score_headline(
                    "Will tech stocks rally?",
                    "Tech stocks surge on AI boom",
                )

    # All three providers were tried
    mock_a.assert_called_once()
    mock_g.assert_called_once()
    mock_o.assert_called_once()

    # Rule-based fallback produced a valid result
    assert isinstance(result, ScoredHeadline)
    assert result.sentiment == "bullish_yes"  # "surge" + "boom"


# ---------------------------------------------------------------------------
# for_agent() proxy tests
# ---------------------------------------------------------------------------


class TestForAgent:
    def test_proxy_has_different_agent_name(self):
        client = LLMClient(chain=["rule-based"], agent_name="unknown")
        proxy = client.for_agent("react_analyst")
        assert proxy._agent_name == "react_analyst"
        assert client._agent_name == "unknown"

    def test_proxy_shares_registry(self):
        client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
        proxy = client.for_agent("test_agent")
        assert proxy.registry is client.registry

    def test_proxy_shares_circuit_breakers(self):
        client = LLMClient(chain=["rule-based"])
        proxy = client.for_agent("test_agent")
        client._record_failure("groq")
        assert proxy._fail_counts.get("groq") == 1

    def test_proxy_shares_cost_ledger(self):
        from unittest.mock import MagicMock

        mock_ledger = MagicMock()
        client = LLMClient(chain=["rule-based"], cost_ledger=mock_ledger)
        proxy = client.for_agent("test_agent")
        assert proxy._cost_ledger is mock_ledger

    @pytest.mark.asyncio
    async def test_proxy_resolves_same_chain(self):
        client = LLMClient(chain=["ollama", "rule-based"])
        proxy = client.for_agent("test_agent")
        parent_chain = await client._resolve_chain()
        proxy_chain = await proxy._resolve_chain()
        assert parent_chain == proxy_chain
