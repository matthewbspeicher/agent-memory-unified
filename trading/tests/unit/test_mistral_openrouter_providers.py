"""Tests for MistralProvider and OpenRouterProvider.

Mirrors test_cerebras_provider.py — both new providers are OpenAI-compatible
free-tier additions filling the same role as Cerebras: a fallback when
paid providers hit billing caps.

Mistral diversifies the model family (Llama-shaped failures sometimes
correlate across Groq/Cerebras/OpenRouter; Mistral's models don't).

OpenRouter is a meta-provider — one integration unlocks dozens of free
and paid models, so it doubles as a long-tail fallback.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm.client import LLMClient
from llm.providers import (
    LLMResult,
    MistralProvider,
    OpenRouterProvider,
    ProviderName,
)


def _mock_openai_response(text: str = "ok", prompt_tokens: int = 10, completion_tokens: int = 3):
    """Helper: build a mock openai response with the standard usage shape."""
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=text))]
    response.usage = MagicMock(
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )
    return response


def _mock_async_openai_client(response):
    """Helper: async context manager that yields a client returning *response*."""
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


# ---------------------------------------------------------------------------
# MistralProvider
# ---------------------------------------------------------------------------


class TestMistralProvider:
    def test_name_and_default_model(self):
        p = MistralProvider(api_key="m-test")
        assert p.name == "mistral"
        assert p.model == "mistral-small-latest"

    @pytest.mark.asyncio
    async def test_complete_targets_mistral_base_url(self):
        p = MistralProvider(api_key="m-test")
        mock = _mock_async_openai_client(_mock_openai_response(text="bullish"))
        with patch("openai.AsyncOpenAI", return_value=mock) as openai_ctor:
            result = await p.complete("x")
        kwargs = openai_ctor.call_args.kwargs
        assert kwargs["base_url"] == "https://api.mistral.ai/v1"
        assert kwargs["api_key"] == "m-test"
        assert result is not None
        assert result.provider == "mistral"
        assert result.text == "bullish"

    @pytest.mark.asyncio
    async def test_chat_works(self):
        p = MistralProvider(api_key="m-test", model="open-mistral-7b")
        mock = _mock_async_openai_client(_mock_openai_response("hi"))
        with patch("openai.AsyncOpenAI", return_value=mock):
            result = await p.chat(
                system="be terse", messages=[{"role": "user", "content": "hi"}]
            )
        assert result is not None
        assert result.provider == "mistral"
        assert result.model == "open-mistral-7b"

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        p = MistralProvider(api_key="m-test")
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=RuntimeError("down"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        with patch("openai.AsyncOpenAI", return_value=client):
            assert await p.complete("x") is None
            assert await p.chat("s", [{"role": "user", "content": "x"}]) is None


# ---------------------------------------------------------------------------
# OpenRouterProvider
# ---------------------------------------------------------------------------


class TestOpenRouterProvider:
    def test_name_and_default_model(self):
        p = OpenRouterProvider(api_key="or-test")
        assert p.name == "openrouter"
        assert p.model == "meta-llama/llama-3.1-8b-instruct:free"

    @pytest.mark.asyncio
    async def test_complete_targets_openrouter_base_url(self):
        p = OpenRouterProvider(api_key="or-test")
        mock = _mock_async_openai_client(_mock_openai_response("growth"))
        with patch("openai.AsyncOpenAI", return_value=mock) as openai_ctor:
            result = await p.complete("Analyze NVDA")
        kwargs = openai_ctor.call_args.kwargs
        assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
        assert kwargs["api_key"] == "or-test"
        # OpenRouter expects HTTP-Referer + X-Title for free-tier attribution
        assert "default_headers" in kwargs
        headers = kwargs["default_headers"]
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers
        assert result is not None
        assert result.provider == "openrouter"
        assert result.text == "growth"

    @pytest.mark.asyncio
    async def test_custom_headers(self):
        p = OpenRouterProvider(
            api_key="or-test",
            http_referer="https://example.com",
            app_title="custom title",
        )
        mock = _mock_async_openai_client(_mock_openai_response())
        with patch("openai.AsyncOpenAI", return_value=mock) as openai_ctor:
            await p.complete("x")
        headers = openai_ctor.call_args.kwargs["default_headers"]
        assert headers["HTTP-Referer"] == "https://example.com"
        assert headers["X-Title"] == "custom title"

    @pytest.mark.asyncio
    async def test_can_pick_a_free_qwen_model(self):
        """Sanity check that the model parameter flows through end-to-end."""
        p = OpenRouterProvider(
            api_key="or-test",
            model="qwen/qwen-2.5-72b-instruct:free",
        )
        mock = _mock_async_openai_client(_mock_openai_response())
        with patch("openai.AsyncOpenAI", return_value=mock) as _:
            result = await p.complete("x")
        assert result is not None
        assert result.model == "qwen/qwen-2.5-72b-instruct:free"

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        p = OpenRouterProvider(api_key="or-test")
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=RuntimeError("down"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        with patch("openai.AsyncOpenAI", return_value=client):
            assert await p.complete("x") is None
            assert await p.chat("s", [{"role": "user", "content": "x"}]) is None


# ---------------------------------------------------------------------------
# LLMClient wiring + chain
# ---------------------------------------------------------------------------


class TestClientWiring:
    def test_mistral_registered_when_key_set(self):
        client = LLMClient(mistral_key="m-test")
        assert client.registry.get("mistral") is not None

    def test_openrouter_registered_when_key_set(self):
        client = LLMClient(openrouter_key="or-test")
        assert client.registry.get("openrouter") is not None

    def test_neither_registered_without_keys(self):
        client = LLMClient()
        assert client.registry.get("mistral") is None
        assert client.registry.get("openrouter") is None

    def test_default_chain_includes_all_free_providers(self):
        """All 4 free-tier providers (cerebras/gemini/mistral/openrouter)
        must be in the default chain so the fallback actually tries them."""
        client = LLMClient()
        for name in ("cerebras", "gemini", "mistral", "openrouter"):
            assert name in client._chain, f"{name} missing from default chain"

    def test_chain_order_paid_before_free_before_local(self):
        """Paid → free-tier hosted → local ollama → rule-based."""
        client = LLMClient()
        chain = client._chain
        # Paid tier comes first
        assert chain.index("anthropic") < chain.index("cerebras")
        assert chain.index("bedrock") < chain.index("mistral")
        # Free hosted before local
        assert chain.index("openrouter") < chain.index("ollama")
        # Mistral diversification: before openrouter (Mistral's models are
        # not Llama-family — uncorrelated failures)
        assert chain.index("mistral") < chain.index("openrouter")
        # rule-based is always last
        assert chain[-1] == "rule-based"

    def test_provider_name_literal_includes_both(self):
        allowed = set(ProviderName.__args__)
        assert "mistral" in allowed
        assert "openrouter" in allowed


# ---------------------------------------------------------------------------
# End-to-end fallback
# ---------------------------------------------------------------------------


class TestEndToEndFallback:
    @pytest.mark.asyncio
    async def test_paid_dead_groq_dead_cerebras_dead_mistral_picks_up(self):
        """Reproduces the 2026-05-23 incident shape with more depth: the
        first 4 providers all return None, mistral succeeds."""
        mistral_result = LLMResult(
            text="mistral output", provider="mistral", model="mistral-small-latest"
        )
        client = LLMClient(
            anthropic_key="a-x",
            groq_key="g-x",
            cerebras_key="c-x",
            mistral_key="m-x",
            chain=["anthropic", "groq", "cerebras", "mistral", "rule-based"],
        )
        with patch.object(
            client.registry.get("anthropic"),
            "complete",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            client.registry.get("groq"),
            "complete",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            client.registry.get("cerebras"),
            "complete",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            client.registry.get("mistral"),
            "complete",
            new_callable=AsyncMock,
            return_value=mistral_result,
        ):
            result = await client.complete("test")
        assert result.provider == "mistral"
        assert result.text == "mistral output"

    @pytest.mark.asyncio
    async def test_openrouter_picks_up_when_all_others_dead(self):
        or_result = LLMResult(
            text="openrouter output",
            provider="openrouter",
            model="meta-llama/llama-3.1-8b-instruct:free",
        )
        client = LLMClient(
            groq_key="g-x",
            openrouter_key="or-x",
            chain=["groq", "openrouter", "rule-based"],
        )
        with patch.object(
            client.registry.get("groq"),
            "complete",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            client.registry.get("openrouter"),
            "complete",
            new_callable=AsyncMock,
            return_value=or_result,
        ):
            result = await client.complete("test")
        assert result.provider == "openrouter"
