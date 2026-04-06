"""
Unified LLM client with automatic fallback chain.

Tries providers in order: Anthropic → Groq → Ollama → rule-based.
Each provider is tested with a minimal health check; failures cascade to the next.

Usage:
    from llm.client import LLMClient

    client = LLMClient(
        anthropic_key="sk-...",
        groq_key="gsk_...",
        ollama_url="http://localhost:11434",
        chain=["anthropic", "groq", "ollama", "rule-based"],
    )
    result = await client.complete("Rate this headline...", model="haiku")
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

ProviderName = Literal["anthropic", "bedrock", "groq", "ollama", "rule-based"]


@dataclass
class LLMResult:
    """Structured result from any LLM provider."""

    text: str
    provider: ProviderName
    model: str
    latency_ms: float = 0.0


@dataclass
class ScoredHeadline:
    """Standardized headline scoring output (used by RSS/NewsAPI sources)."""

    relevance: float  # 0.0 - 1.0
    sentiment: str  # bullish_yes | bearish_yes | neutral
    mispricing_score: float  # -1.0 to +1.0


@dataclass
class ProbabilityEstimate:
    """Standardized probability estimate output (used by kalshi_news_arb)."""

    implied_probability: float  # 0.01 - 0.99
    confidence: int  # 0 - 100
    reasoning: str


# ---------------------------------------------------------------------------
# Rule-based fallbacks (zero cost, always available)
# ---------------------------------------------------------------------------

_BULLISH_WORDS = {
    "surge",
    "soar",
    "rally",
    "beat",
    "exceed",
    "growth",
    "upgrade",
    "jump",
    "gain",
    "rise",
    "climb",
    "record",
    "strong",
    "boom",
    "breakthrough",
    "lift",
    "improve",
    "recovery",
    "optimistic",
    "bullish",
    "outperform",
    "gain",
    "profit",
    "profitable",
    "dividend",
    "buyback",
    "expansion",
    "hire",
}
_BEARISH_WORDS = {
    "miss",
    "plunge",
    "crash",
    "downgrade",
    "layoff",
    "loss",
    "cut",
    "drop",
    "fall",
    "decline",
    "fear",
    "warning",
    "risk",
    "concern",
    "weak",
    "slow",
    "bankruptcy",
    "lawsuit",
    "fraud",
    "investigation",
    "default",
    "deficit",
    "bearish",
    "underperform",
    "sell",
    "downsize",
    "restructure",
    "recall",
}


def _rule_based_score_headline(headline: str) -> ScoredHeadline:
    """Keyword-based headline scoring — no LLM required."""
    hl = headline.lower()
    bull = sum(1 for w in _BULLISH_WORDS if w in hl)
    bear = sum(1 for w in _BEARISH_WORDS if w in hl)
    total = bull + bear

    if total == 0:
        return ScoredHeadline(relevance=0.3, sentiment="neutral", mispricing_score=0.0)

    bull_ratio = bull / total
    if bull_ratio > 0.6:
        sentiment = "bullish_yes"
        mispricing = 0.3 * bull_ratio
    elif bull_ratio < 0.4:
        sentiment = "bearish_yes"
        mispricing = -0.3 * (1 - bull_ratio)
    else:
        sentiment = "neutral"
        mispricing = 0.0

    relevance = min(0.8, 0.2 + 0.3 * total)
    return ScoredHeadline(
        relevance=relevance, sentiment=sentiment, mispricing_score=round(mispricing, 3)
    )


def _rule_based_probability(question: str, headlines: list[str]) -> ProbabilityEstimate:
    """Simple keyword overlap heuristic for probability estimation."""
    q_words = set(question.lower().split())
    h_text = " ".join(headlines).lower()
    h_words = set(h_text.split())

    overlap = len(q_words & h_words)
    total_q = len(q_words) or 1

    # Crude: more overlap = higher YES probability
    base = 0.5
    if overlap > 0:
        base = min(0.8, 0.5 + (overlap / total_q) * 0.3)

    # Check for negation words
    negations = {"not", "no", "never", "neither", "nobody", "nothing", "nowhere", "nor"}
    if q_words & negations:
        base = 1.0 - base

    return ProbabilityEstimate(
        implied_probability=round(base, 2),
        confidence=min(70, 30 + overlap * 5),
        reasoning=f"Keyword overlap heuristic ({overlap}/{total_q} words matched)",
    )


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


async def _try_anthropic(
    prompt: str,
    *,
    api_key: str,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 200,
) -> LLMResult | None:
    """Call Anthropic Claude API."""
    try:
        import anthropic
        import time

        start = time.monotonic()
        client = anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        latency = (time.monotonic() - start) * 1000
        return LLMResult(
            text=msg.content[0].text.strip(),
            provider="anthropic",
            model=model,
            latency_ms=round(latency),
        )
    except Exception as exc:
        logger.warning("Anthropic failed: %s", exc)
        return None


async def _try_bedrock(
    prompt: str,
    *,
    region: str,
    model: str = "anthropic.claude-3-haiku-20240307-v1:0",
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    max_tokens: int = 200,
) -> LLMResult | None:
    """Call AWS Bedrock API."""
    try:
        import boto3
        import json
        import time

        start = time.monotonic()

        # Create boto3 client with explicit credentials if provided, else use IAM role
        if access_key_id and secret_access_key:
            client = boto3.client(
                "bedrock-runtime",
                region_name=region,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
            )
        else:
            client = boto3.client("bedrock-runtime", region_name=region)

        # Bedrock request format for Claude models
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        })

        response = client.invoke_model(
            modelId=model,
            body=body,
        )

        response_body = json.loads(response["body"].read())
        latency = (time.monotonic() - start) * 1000

        return LLMResult(
            text=response_body["content"][0]["text"].strip(),
            provider="bedrock",
            model=model,
            latency_ms=round(latency),
        )
    except Exception as exc:
        logger.warning("Bedrock failed: %s", exc)
        return None


async def _try_groq(
    prompt: str,
    *,
    api_key: str,
    model: str = "llama-3.3-70b-versatile",
    max_tokens: int = 200,
) -> LLMResult | None:
    """Call Groq API (OpenAI-compatible)."""
    try:
        import openai
        import time

        start = time.monotonic()
        client = openai.AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        latency = (time.monotonic() - start) * 1000
        return LLMResult(
            text=resp.choices[0].message.content.strip(),
            provider="groq",
            model=model,
            latency_ms=round(latency),
        )
    except Exception as exc:
        logger.warning("Groq failed: %s", exc)
        return None


async def _try_ollama(
    prompt: str,
    *,
    base_url: str = "http://localhost:11434",
    model: str = "llama3.2:3b",
    max_tokens: int = 200,
) -> LLMResult | None:
    """Call local Ollama server (OpenAI-compatible endpoint)."""
    try:
        import openai
        import time

        start = time.monotonic()
        client = openai.AsyncOpenAI(
            base_url=f"{base_url}/v1",
            api_key="ollama",
            timeout=30.0,
        )
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        latency = (time.monotonic() - start) * 1000
        return LLMResult(
            text=resp.choices[0].message.content.strip(),
            provider="ollama",
            model=model,
            latency_ms=round(latency),
        )
    except Exception as exc:
        logger.warning("Ollama failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Chat provider helpers (multi-turn with system prompt)
# ---------------------------------------------------------------------------


async def _try_anthropic_chat(
    system: str,
    messages: list[dict[str, str]],
    *,
    api_key: str,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 500,
) -> LLMResult | None:
    """Call Anthropic Claude API with system prompt + messages."""
    try:
        import anthropic
        import time

        start = time.monotonic()
        client = anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        latency = (time.monotonic() - start) * 1000
        return LLMResult(
            text=msg.content[0].text.strip(),
            provider="anthropic",
            model=model,
            latency_ms=round(latency),
        )
    except Exception as exc:
        logger.warning("Anthropic chat failed: %s", exc)
        return None


async def _try_bedrock_chat(
    system: str,
    messages: list[dict[str, str]],
    *,
    region: str,
    model: str = "anthropic.claude-3-haiku-20240307-v1:0",
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    max_tokens: int = 500,
) -> LLMResult | None:
    """Call AWS Bedrock API with system prompt + messages."""
    try:
        import boto3
        import json
        import time

        start = time.monotonic()

        # Create boto3 client
        if access_key_id and secret_access_key:
            client = boto3.client(
                "bedrock-runtime",
                region_name=region,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
            )
        else:
            client = boto3.client("bedrock-runtime", region_name=region)

        # Bedrock request format for Claude models with system prompt
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        })

        response = client.invoke_model(
            modelId=model,
            body=body,
        )

        response_body = json.loads(response["body"].read())
        latency = (time.monotonic() - start) * 1000

        return LLMResult(
            text=response_body["content"][0]["text"].strip(),
            provider="bedrock",
            model=model,
            latency_ms=round(latency),
        )
    except Exception as exc:
        logger.warning("Bedrock chat failed: %s", exc)
        return None


async def _try_groq_chat(
    system: str,
    messages: list[dict[str, str]],
    *,
    api_key: str,
    model: str = "llama-3.3-70b-versatile",
    max_tokens: int = 500,
) -> LLMResult | None:
    """Call Groq API with system prompt + messages."""
    try:
        import openai
        import time

        start = time.monotonic()
        client = openai.AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
        full_messages = [{"role": "system", "content": system}] + messages
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=full_messages,
        )
        latency = (time.monotonic() - start) * 1000
        return LLMResult(
            text=resp.choices[0].message.content.strip(),
            provider="groq",
            model=model,
            latency_ms=round(latency),
        )
    except Exception as exc:
        logger.warning("Groq chat failed: %s", exc)
        return None


async def _try_ollama_chat(
    system: str,
    messages: list[dict[str, str]],
    *,
    base_url: str = "http://localhost:11434",
    model: str = "llama3.2:3b",
    max_tokens: int = 500,
) -> LLMResult | None:
    """Call local Ollama server with system prompt + messages."""
    try:
        import openai
        import time

        start = time.monotonic()
        client = openai.AsyncOpenAI(
            base_url=f"{base_url}/v1",
            api_key="ollama",
        )
        full_messages = [{"role": "system", "content": system}] + messages
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=full_messages,
        )
        latency = (time.monotonic() - start) * 1000
        return LLMResult(
            text=resp.choices[0].message.content.strip(),
            provider="ollama",
            model=model,
            latency_ms=round(latency),
        )
    except Exception as exc:
        logger.warning("Ollama chat failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Unified client
# ---------------------------------------------------------------------------


class LLMClient:
    """
    Fallback-chain LLM client.

    Tries providers in configured order, returns first success.
    Falls back to rule-based scoring if all providers fail.
    """

    def __init__(
        self,
        anthropic_key: str | None = None,
        groq_key: str | None = None,
        ollama_url: str = "http://localhost:11434",
        bedrock_region: str | None = None,
        bedrock_access_key_id: str | None = None,
        bedrock_secret_access_key: str | None = None,
        chain: list[str] | None = None,
        anthropic_model: str = "claude-haiku-4-5-20251001",
        groq_model: str = "llama-3.3-70b-versatile",
        ollama_model: str = "llama3.2:3b",
        bedrock_model: str = "anthropic.claude-3-haiku-20240307-v1:0",
    ) -> None:
        self._anthropic_key = anthropic_key
        self._groq_key = groq_key
        self._ollama_url = ollama_url
        self._bedrock_region = bedrock_region
        self._bedrock_access_key_id = bedrock_access_key_id
        self._bedrock_secret_access_key = bedrock_secret_access_key
        self._chain: list[ProviderName] = chain or [
            "anthropic",
            "bedrock",
            "groq",
            "ollama",
            "rule-based",
        ]
        self._anthropic_model = anthropic_model
        self._groq_model = groq_model
        self._ollama_model = ollama_model
        self._bedrock_model = bedrock_model

        # Per-provider circuit breaker (disabled after N consecutive failures)
        self._fail_counts: dict[str, int] = {}
        self._disabled: dict[str, bool] = {}
        self._max_fails = 5

    def _is_disabled(self, provider: str) -> bool:
        return self._disabled.get(provider, False)

    def _record_failure(self, provider: str) -> None:
        count = self._fail_counts.get(provider, 0) + 1
        self._fail_counts[provider] = count
        if count >= self._max_fails:
            self._disabled[provider] = True
            logger.warning(
                "LLMClient: %s disabled after %d consecutive failures", provider, count
            )

    def _record_success(self, provider: str) -> None:
        self._fail_counts[provider] = 0
        self._disabled[provider] = False

    def re_enable_all(self) -> None:
        """Re-enable all providers (call after adding API credits)."""
        self._fail_counts.clear()
        self._disabled.clear()
        logger.info("LLMClient: all providers re-enabled")

    async def complete(self, prompt: str, *, max_tokens: int = 200) -> LLMResult:
        """
        Try each provider in chain order. Always returns a result
        (falls back to rule-based if all fail).
        """

        providers = self._resolve_chain()

        for provider in providers:
            if self._is_disabled(provider):
                continue

            result = None
            if provider == "anthropic" and self._anthropic_key:
                result = await _try_anthropic(
                    prompt,
                    api_key=self._anthropic_key,
                    model=self._anthropic_model,
                    max_tokens=max_tokens,
                )
            elif provider == "bedrock" and self._bedrock_region:
                result = await _try_bedrock(
                    prompt,
                    region=self._bedrock_region,
                    model=self._bedrock_model,
                    access_key_id=self._bedrock_access_key_id,
                    secret_access_key=self._bedrock_secret_access_key,
                    max_tokens=max_tokens,
                )
            elif provider == "groq" and self._groq_key:
                result = await _try_groq(
                    prompt,
                    api_key=self._groq_key,
                    model=self._groq_model,
                    max_tokens=max_tokens,
                )
            elif provider == "ollama":
                result = await _try_ollama(
                    prompt,
                    base_url=self._ollama_url,
                    model=self._ollama_model,
                    max_tokens=max_tokens,
                )

            if result:
                self._record_success(provider)
                return result
            else:
                self._record_failure(provider)

        # All providers failed — this should not happen (rule-based always works)
        logger.error("LLMClient: all providers failed, returning empty result")
        return LLMResult(text="", provider="anthropic", model="none")

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 500,
    ) -> LLMResult:
        """
        Multi-turn chat with system prompt. Used by WhatsApp assistant.
        Tries each provider in chain order. Returns first success.
        """
        providers = self._resolve_chain()

        for provider in providers:
            if provider == "rule-based":
                continue  # no rule-based fallback for chat
            if self._is_disabled(provider):
                continue

            result = None
            if provider == "anthropic" and self._anthropic_key:
                result = await _try_anthropic_chat(
                    system,
                    messages,
                    api_key=self._anthropic_key,
                    model=self._anthropic_model,
                    max_tokens=max_tokens,
                )
            elif provider == "bedrock" and self._bedrock_region:
                result = await _try_bedrock_chat(
                    system,
                    messages,
                    region=self._bedrock_region,
                    model=self._bedrock_model,
                    access_key_id=self._bedrock_access_key_id,
                    secret_access_key=self._bedrock_secret_access_key,
                    max_tokens=max_tokens,
                )
            elif provider == "groq" and self._groq_key:
                result = await _try_groq_chat(
                    system,
                    messages,
                    api_key=self._groq_key,
                    model=self._groq_model,
                    max_tokens=max_tokens,
                )
            elif provider == "ollama":
                result = await _try_ollama_chat(
                    system,
                    messages,
                    base_url=self._ollama_url,
                    model=self._ollama_model,
                    max_tokens=max_tokens,
                )

            if result:
                self._record_success(provider)
                return result
            else:
                self._record_failure(provider)

        # All providers failed
        logger.error("LLMClient.chat: all providers failed")
        return LLMResult(
            text="I'm unable to process that right now. Try a /command instead.",
            provider="rule-based",
            model="none",
        )

    async def score_headline(
        self,
        contract_title: str,
        headline: str,
    ) -> ScoredHeadline:
        """
        Score a headline against a prediction market contract.
        Tries LLM providers, falls back to rule-based scoring.
        """
        prompt = (
            f"You are a calibrated prediction market analyst.\n\n"
            f"Contract: {contract_title}\n"
            f"Headline: {headline}\n\n"
            f"Rate this headline's impact on the contract's YES outcome.\n"
            f"Reply with ONLY valid JSON, no markdown:\n"
            f'{{"relevance": <0.0-1.0>, '
            f'"sentiment": "<bullish_yes|bearish_yes|neutral>", '
            f'"mispricing_score": <-1.0 to +1.0, positive=YES underpriced>}}'
        )

        # Try LLM providers
        providers = self._resolve_chain()
        for provider in providers:
            if provider == "rule-based":
                continue
            if self._is_disabled(provider):
                continue

            result = None
            if provider == "anthropic" and self._anthropic_key:
                result = await _try_anthropic(
                    prompt, api_key=self._anthropic_key, model=self._anthropic_model
                )
            elif provider == "bedrock" and self._bedrock_region:
                result = await _try_bedrock(
                    prompt,
                    region=self._bedrock_region,
                    model=self._bedrock_model,
                    access_key_id=self._bedrock_access_key_id,
                    secret_access_key=self._bedrock_secret_access_key,
                )
            elif provider == "groq" and self._groq_key:
                result = await _try_groq(
                    prompt, api_key=self._groq_key, model=self._groq_model
                )
            elif provider == "ollama":
                result = await _try_ollama(
                    prompt, base_url=self._ollama_url, model=self._ollama_model
                )

            if result and result.text:
                self._record_success(provider)
                try:
                    # Extract JSON from response
                    match = re.search(r"\{.*\}", result.text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(0))
                        return ScoredHeadline(
                            relevance=float(
                                max(0.0, min(1.0, data.get("relevance", 0.0)))
                            ),
                            sentiment=str(data.get("sentiment", "neutral")),
                            mispricing_score=float(
                                max(-1.0, min(1.0, data.get("mispricing_score", 0.0)))
                            ),
                        )
                except (json.JSONDecodeError, ValueError):
                    pass
            else:
                self._record_failure(provider)

        # Rule-based fallback — always available
        logger.debug("LLMClient: using rule-based fallback for headline scoring")
        return _rule_based_score_headline(headline)

    async def estimate_probability(
        self,
        question: str,
        headlines: list[str],
    ) -> ProbabilityEstimate:
        """
        Estimate probability from headlines.
        Tries LLM providers, falls back to rule-based heuristic.
        """
        headlines_text = (
            "\n".join(f"- {h}" for h in headlines)
            if headlines
            else "(no recent headlines)"
        )
        prompt = (
            f"You are a calibrated probability forecaster.\n\n"
            f"Question: {question}\n\n"
            f"Recent headlines:\n{headlines_text}\n\n"
            f"Based only on the question and headlines above, estimate the probability that the answer is YES.\n"
            f"Reply with ONLY valid JSON and absolutely no markdown formatting or other text.\n"
            f"The JSON must contain:\n"
            f'- "implied_probability": A float 0.00-1.00\n'
            f'- "confidence": An integer 0-100\n'
            f'- "reasoning": A short string\n'
        )

        providers = self._resolve_chain()
        for provider in providers:
            if provider == "rule-based":
                continue
            if self._is_disabled(provider):
                continue

            result = None
            if provider == "anthropic" and self._anthropic_key:
                result = await _try_anthropic(
                    prompt, api_key=self._anthropic_key, model=self._anthropic_model
                )
            elif provider == "bedrock" and self._bedrock_region:
                result = await _try_bedrock(
                    prompt,
                    region=self._bedrock_region,
                    model=self._bedrock_model,
                    access_key_id=self._bedrock_access_key_id,
                    secret_access_key=self._bedrock_secret_access_key,
                )
            elif provider == "groq" and self._groq_key:
                result = await _try_groq(
                    prompt, api_key=self._groq_key, model=self._groq_model
                )
            elif provider == "ollama":
                result = await _try_ollama(
                    prompt, base_url=self._ollama_url, model=self._ollama_model
                )

            if result and result.text:
                self._record_success(provider)
                try:
                    match = re.search(r"\{.*\}", result.text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(0))
                        return ProbabilityEstimate(
                            implied_probability=max(
                                0.01,
                                min(0.99, float(data.get("implied_probability", 0.5))),
                            ),
                            confidence=max(
                                0, min(100, int(data.get("confidence", 50)))
                            ),
                            reasoning=str(data.get("reasoning", "")),
                        )
                except (json.JSONDecodeError, ValueError):
                    pass
            else:
                self._record_failure(provider)

        # Rule-based fallback
        logger.debug("LLMClient: using rule-based fallback for probability estimate")
        return _rule_based_probability(question, headlines)

    def _resolve_chain(self) -> list[str]:
        """Return chain filtered to available providers."""
        chain = list(self._chain)
        # Remove providers that lack credentials
        if "anthropic" in chain and not self._anthropic_key:
            chain.remove("anthropic")
        if "bedrock" in chain and not self._bedrock_region:
            chain.remove("bedrock")
        if "groq" in chain and not self._groq_key:
            chain.remove("groq")
        # rule-based is always last
        return chain
