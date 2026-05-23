"""Tests for the CerebrasProvider and its place in the LLMClient chain.

Cerebras is an OpenAI-compatible free-tier LLM provider added after a
production incident on 2026-05-23 where all paid providers (Anthropic,
Groq, OpenAI) and the local Ollama (miniPC offline) were unavailable
simultaneously.  Cerebras + Gemini together give the engine two
free-tier fallbacks before it has to degrade to rule-based.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm.client import LLMClient
from llm.providers import CerebrasProvider, LLMResult, ProviderName


# ---------------------------------------------------------------------------
# Provider basics
# ---------------------------------------------------------------------------


class TestCerebrasProvider:
    def test_name_is_cerebras(self):
        p = CerebrasProvider(api_key="csk-test")
        assert p.name == "cerebras"

    def test_default_model(self):
        p = CerebrasProvider(api_key="csk-test")
        assert p.model == "llama-3.3-70b"

    def test_custom_model(self):
        p = CerebrasProvider(api_key="csk-test", model="llama-3.1-8b")
        assert p.model == "llama-3.1-8b"

    @pytest.mark.asyncio
    async def test_complete_calls_cerebras_base_url(self):
        """Verify the OpenAI-compatible client targets api.cerebras.ai."""
        p = CerebrasProvider(api_key="csk-test")

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="bullish on AAPL"))
        ]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("openai.AsyncOpenAI", return_value=mock_client) as mock_openai:
            result = await p.complete("Analyze AAPL")

        # Confirm base_url is Cerebras
        mock_openai.assert_called_once()
        kwargs = mock_openai.call_args.kwargs
        assert kwargs["base_url"] == "https://api.cerebras.ai/v1"
        assert kwargs["api_key"] == "csk-test"

        # Result shape
        assert result is not None
        assert result.text == "bullish on AAPL"
        assert result.provider == "cerebras"
        assert result.model == "llama-3.3-70b"
        assert result.input_tokens == 10
        assert result.output_tokens == 5

    @pytest.mark.asyncio
    async def test_complete_returns_none_on_exception(self):
        p = CerebrasProvider(api_key="csk-test")
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("api down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await p.complete("x")
        assert result is None

    @pytest.mark.asyncio
    async def test_chat_works(self):
        p = CerebrasProvider(api_key="csk-test")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = MagicMock(prompt_tokens=8, completion_tokens=2)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await p.chat(
                system="be terse", messages=[{"role": "user", "content": "hi"}]
            )
        assert result is not None
        assert result.text == "ok"
        assert result.provider == "cerebras"


# ---------------------------------------------------------------------------
# LLMClient wiring
# ---------------------------------------------------------------------------


class TestCerebrasInLLMClient:
    def test_registered_when_key_provided(self):
        client = LLMClient(cerebras_key="csk-test")
        assert client.registry.get("cerebras") is not None
        assert client.registry.get("cerebras").model == "llama-3.3-70b"

    def test_not_registered_without_key(self):
        client = LLMClient()  # no keys
        assert client.registry.get("cerebras") is None

    def test_custom_model(self):
        client = LLMClient(cerebras_key="csk-test", cerebras_model="llama-3.1-8b")
        assert client.registry.get("cerebras").model == "llama-3.1-8b"

    def test_default_chain_includes_cerebras_and_gemini(self):
        """Both free-tier providers must be in the default chain so they're
        actually tried during fallback. Pre-incident, gemini was registered
        but not in the chain — fixed alongside the Cerebras add."""
        client = LLMClient()
        assert "cerebras" in client._chain
        assert "gemini" in client._chain
        # Order: free-tier hosted should come BEFORE local ollama
        # (network is generally more reliable than local LLM).
        cerebras_idx = client._chain.index("cerebras")
        gemini_idx = client._chain.index("gemini")
        ollama_idx = client._chain.index("ollama")
        assert cerebras_idx < ollama_idx
        assert gemini_idx < ollama_idx
        # And after the paid providers
        groq_idx = client._chain.index("groq")
        assert cerebras_idx > groq_idx


# ---------------------------------------------------------------------------
# Fallback behaviour: paid dead, free tier picks up
# ---------------------------------------------------------------------------


class TestFallbackToCerebras:
    @pytest.mark.asyncio
    async def test_falls_back_to_cerebras_when_paid_providers_fail(self):
        """Reproduces the 2026-05-23 incident shape: paid providers all
        fail, cerebras succeeds. Before this provider existed the chain
        would degrade straight to ollama (offline) or rule-based."""
        mock_result = LLMResult(
            text="cerebras response", provider="cerebras", model="llama-3.3-70b"
        )

        client = LLMClient(
            groq_key="gsk-test",
            cerebras_key="csk-test",
            chain=["groq", "cerebras", "rule-based"],
        )
        with patch.object(
            client.registry.get("groq"),
            "complete",
            new_callable=AsyncMock,
            return_value=None,  # paid provider fails
        ):
            with patch.object(
                client.registry.get("cerebras"),
                "complete",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                result = await client.complete("test prompt")

        assert result.text == "cerebras response"
        assert result.provider == "cerebras"


# ---------------------------------------------------------------------------
# ProviderName Literal
# ---------------------------------------------------------------------------


class TestProviderNameLiteral:
    def test_cerebras_and_gemini_in_literal(self):
        """Pre-incident, GeminiProvider's `name = 'gemini'` was not in the
        ProviderName Literal — runtime worked but mypy didn't.  Fixed
        alongside Cerebras add."""
        # The Literal's __args__ is the set of allowed values
        allowed = set(ProviderName.__args__)
        assert "cerebras" in allowed
        assert "gemini" in allowed
        assert "anthropic" in allowed
        assert "groq" in allowed
        assert "ollama" in allowed
        assert "rule-based" in allowed
