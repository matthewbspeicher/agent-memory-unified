"""
Unit tests for the unified LLMClient fallback chain.

All provider calls are mocked — no API keys required.
Tests cover: fallback ordering, circuit breaker, rule-based scoring,
structured parsing (score_headline, estimate_probability), and chat().
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

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
    def test_removes_providers_without_keys(self):
        client = LLMClient(
            anthropic_key=None,
            groq_key=None,
            chain=["anthropic", "groq", "ollama", "rule-based"],
        )
        chain = client._resolve_chain()
        assert "anthropic" not in chain
        assert "groq" not in chain
        assert "ollama" in chain
        assert "rule-based" in chain

    def test_keeps_providers_with_keys(self):
        client = LLMClient(
            anthropic_key="sk-test",
            groq_key="gsk-test",
            chain=["anthropic", "groq", "ollama", "rule-based"],
        )
        chain = client._resolve_chain()
        assert chain == ["anthropic", "groq", "ollama", "rule-based"]

    def test_custom_chain_order(self):
        client = LLMClient(
            groq_key="gsk-test",
            chain=["groq", "ollama", "rule-based"],
        )
        chain = client._resolve_chain()
        assert chain[0] == "groq"


# ---------------------------------------------------------------------------
# complete() fallback tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_uses_first_available_provider():
    """First provider succeeds — no fallback needed."""
    mock_result = LLMResult(text="test response", provider="groq", model="llama-3.3-70b-versatile")

    with patch("llm.client._try_groq", new_callable=AsyncMock, return_value=mock_result):
        client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
        result = await client.complete("test prompt")

    assert result.text == "test response"
    assert result.provider == "groq"


@pytest.mark.asyncio
async def test_complete_falls_back_on_provider_failure():
    """First provider fails, second succeeds."""
    mock_result = LLMResult(text="ollama response", provider="ollama", model="llama3.2:3b")

    with patch("llm.client._try_groq", new_callable=AsyncMock, return_value=None):
        with patch("llm.client._try_ollama", new_callable=AsyncMock, return_value=mock_result):
            client = LLMClient(groq_key="gsk-test", chain=["groq", "ollama", "rule-based"])
            result = await client.complete("test prompt")

    assert result.text == "ollama response"
    assert result.provider == "ollama"


@pytest.mark.asyncio
async def test_complete_records_failures():
    """Failed provider gets failure recorded."""
    with patch("llm.client._try_groq", new_callable=AsyncMock, return_value=None):
        with patch("llm.client._try_ollama", new_callable=AsyncMock, return_value=None):
            client = LLMClient(groq_key="gsk-test", chain=["groq", "ollama", "rule-based"])
            await client.complete("test prompt")

    assert client._fail_counts.get("groq", 0) == 1
    assert client._fail_counts.get("ollama", 0) == 1


@pytest.mark.asyncio
async def test_complete_skips_disabled_providers():
    """Disabled provider is skipped, next one is tried."""
    mock_result = LLMResult(text="ollama response", provider="ollama", model="llama3.2:3b")

    with patch("llm.client._try_groq", new_callable=AsyncMock) as mock_groq:
        with patch("llm.client._try_ollama", new_callable=AsyncMock, return_value=mock_result):
            client = LLMClient(groq_key="gsk-test", chain=["groq", "ollama", "rule-based"])
            # Disable groq via circuit breaker
            for _ in range(5):
                client._record_failure("groq")

            result = await client.complete("test prompt")

    mock_groq.assert_not_called()
    assert result.provider == "ollama"


# ---------------------------------------------------------------------------
# chat() fallback tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_uses_first_available():
    mock_result = LLMResult(text="chat response", provider="groq", model="llama-3.3-70b-versatile")

    with patch("llm.client._try_groq_chat", new_callable=AsyncMock, return_value=mock_result):
        client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
        result = await client.chat("You are helpful.", [{"role": "user", "content": "Hi"}])

    assert result.text == "chat response"
    assert result.provider == "groq"


@pytest.mark.asyncio
async def test_chat_skips_rule_based():
    """Chat has no rule-based fallback — returns error message instead."""
    with patch("llm.client._try_ollama_chat", new_callable=AsyncMock, return_value=None):
        client = LLMClient(chain=["ollama", "rule-based"])
        result = await client.chat("You are helpful.", [{"role": "user", "content": "Hello"}])

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

    with patch("llm.client._try_groq", new_callable=AsyncMock, return_value=mock_result):
        client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
        result = await client.score_headline("Will AAPL rise?", "Apple reports record Q4")

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

    with patch("llm.client._try_groq", new_callable=AsyncMock, return_value=mock_result):
        client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
        result = await client.score_headline("Test", "Test headline")

    assert result.relevance == 1.0  # clamped from 2.5
    assert result.mispricing_score == -1.0  # clamped from -3.0


@pytest.mark.asyncio
async def test_score_headline_falls_back_to_rules_on_bad_json():
    """Unparseable LLM output triggers rule-based fallback."""
    mock_result = LLMResult(text="Sorry, I cannot parse that.", provider="groq", model="test")

    with patch("llm.client._try_groq", new_callable=AsyncMock, return_value=mock_result):
        client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
        result = await client.score_headline("Test contract", "Stocks surge on growth")

    assert isinstance(result, ScoredHeadline)
    # Rule-based should detect "surge" and "growth"
    assert result.sentiment == "bullish_yes"


@pytest.mark.asyncio
async def test_score_headline_all_providers_fail_uses_rules():
    """All providers fail — rule-based always works."""
    client = LLMClient(chain=["rule-based"])
    result = await client.score_headline("Will oil prices drop?", "Oil prices plunge on oversupply")

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

    with patch("llm.client._try_ollama", new_callable=AsyncMock, return_value=mock_result):
        client = LLMClient(chain=["ollama", "rule-based"])
        result = await client.estimate_probability("Will X happen?", ["X is very likely"])

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

    with patch("llm.client._try_groq", new_callable=AsyncMock, return_value=mock_result):
        client = LLMClient(groq_key="gsk-test", chain=["groq", "rule-based"])
        result = await client.estimate_probability("Test?", ["test"])

    assert result.implied_probability == 0.99  # clamped
    assert result.confidence == 100  # clamped


@pytest.mark.asyncio
async def test_estimate_probability_falls_back_to_rules():
    client = LLMClient(chain=["rule-based"])
    result = await client.estimate_probability("Will inflation rise?", ["inflation rising fast"])

    assert isinstance(result, ProbabilityEstimate)
    assert 0.01 <= result.implied_probability <= 0.99
    assert "overlap" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# Integration: full fallback chain simulation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_chain_anthropic_to_groq_to_rules():
    """Simulates Anthropic failing, Groq failing, falling back to rules."""
    with patch("llm.client._try_anthropic", new_callable=AsyncMock, return_value=None) as mock_a:
        with patch("llm.client._try_groq", new_callable=AsyncMock, return_value=None) as mock_g:
            with patch("llm.client._try_ollama", new_callable=AsyncMock, return_value=None) as mock_o:
                client = LLMClient(
                    anthropic_key="sk-test",
                    groq_key="gsk-test",
                    chain=["anthropic", "groq", "ollama", "rule-based"],
                )
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
