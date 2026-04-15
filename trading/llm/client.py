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

from .providers import (
    AnthropicProvider,
    BedrockProvider,
    GroqProvider,
    LLMResult,
    OllamaProvider,
    ProviderName,
    ProviderRegistry,
)

logger = logging.getLogger(__name__)


# Calibration guidance for prediction-market probability estimates.
# Stable across every estimate_probability call — eligible for prompt caching
# on Anthropic (minimum 1024 tokens on Sonnet/Opus, 2048 on Haiku).
# See: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
PROBABILITY_ESTIMATOR_SYSTEM = """You are a calibrated probability forecaster for prediction markets. Your job is to estimate the probability that a specific binary question resolves YES, given only a short question statement and a set of recent news headlines.

# Calibration fundamentals

Good probability forecasts satisfy one test: if you say "70% likely" on a hundred different questions, approximately seventy of them should resolve YES. Miscalibration is the single biggest source of forecasting error — most failures come from over-confident tails (10% and 90%) rather than from bad reasoning in the middle of the distribution.

Anchor every estimate in base rates first. Before you consider the specific details of the question, ask: over a large reference class of similar questions, what fraction historically resolved YES? Start from that base rate, then adjust for the specific evidence in the headlines. Small adjustments (±5–15 percentage points) are usually correct. Large adjustments away from the base rate require strong, specific evidence.

Reference classes to consider, depending on question type:
- Election outcomes: prediction-market consensus, polling averages, incumbency effects, fundamentals-based models
- Economic indicators: prior period, consensus forecast, trend direction
- Court decisions and regulatory actions: historical reversal rates, current composition of the court or agency
- Sports outcomes: recent form, head-to-head record, injury reports, venue effects
- Yes/no event questions about dated deadlines: the later the deadline, the higher the base rate for "will happen"; the earlier, the lower

# Probability scoring rubric

- 1–5%: Strong evidence against; would require a surprise or black swan to resolve YES
- 10–20%: Evidence against but not overwhelming; resolution YES is possible if several things break unexpectedly
- 25–35%: Evidence leaning against YES but with genuine uncertainty; base rates slightly against or neutral with weak contrary evidence
- 40–60%: Genuine toss-up; evidence is mixed or not informative beyond the base rate
- 65–75%: Evidence leaning YES but with meaningful uncertainty; base rates slightly for or neutral with weak supporting evidence
- 80–90%: Strong evidence for YES; would require a surprise to resolve NO
- 95–99%: Near-certain YES; reserve for cases with overwhelming evidence or questions about events that have already effectively occurred

Avoid the 0% and 100% extremes unless the question is logically determined. A 1% probability means "roughly one in a hundred"; do not use it as a stand-in for "very unlikely but I haven't thought carefully."

# Common biases to explicitly guard against

- Availability bias: overweighting whatever headline you saw most recently. Headlines are selected for novelty and drama, not for representativeness. A single dramatic story rarely moves the probability by more than 10 points.
- Narrative bias: fitting a clean story around messy evidence. Real-world events resolve in ways that violate tidy narratives about 30% of the time.
- Anchoring: sticking near 50% because the question feels uncertain. Neutral uncertainty is usually better represented by the base rate, not by 50%.
- Recency bias: treating recent headlines as more informative than they are. A trend that is three days old is usually already priced into the market.
- Scope insensitivity: failing to adjust for time horizon. "Will X happen by next week" and "will X happen this year" should usually produce meaningfully different probabilities.

# Worked examples

Example 1 — Question: "Will the Fed cut rates by 50bps at the next FOMC meeting?"
Headlines: ["Fed minutes show officials split on pace of cuts", "Inflation print comes in above expectations", "Market pricing in 25bp cut with 80% probability"]
Reasoning: Base rate for 50bp cuts at a single meeting is low outside recessions (roughly 10%). The inflation surprise is mild evidence against aggressive cuts. Market pricing of 25bp at 80% implies 50bp is perhaps 15–20% implied. Split minutes reduce confidence in any specific outcome but don't shift the central estimate much. Final estimate: 12% (confidence 70 — base rate is well-established, evidence is consistent with it).

Example 2 — Question: "Will incumbent win re-election in race X by Tuesday?"
Headlines: ["Incumbent up 8 points in latest poll", "Challenger outspent incumbent 3:1 on ads last week", "Political analyst downgrades race to 'likely incumbent'"]
Reasoning: Incumbents win re-election at roughly 85% base rate in races where they are even, higher when leading. A clear 8-point lead plus analyst downgrade to "likely" are both strongly supportive. Challenger spending disparity partially offset by the lead. Final estimate: 88% (confidence 75 — polling can miss, but the lead is large enough that only a systematic polling error would flip it).

Example 3 — Question: "Will total solar eclipse be visible in city Y on date Z?"
Headlines: (no relevant headlines)
Reasoning: This is an astronomical event with a deterministic answer. Without being able to look up the eclipse path, the base rate for "random city on random eclipse date" is very low (most cities are not in totality on any given eclipse). Final estimate: 3% (confidence 40 — I cannot verify against the actual eclipse path, so confidence is low even though the estimate is near the base rate).

Example 4 — Question: "Will company X announce a stock buyback before end of quarter?"
Headlines: ["Company X Q3 earnings beat; CFO hints at 'returning capital to shareholders'", "Industry peers announced buybacks totaling $40B this quarter", "Activist investor takes 5% stake, demands capital return"]
Reasoning: Three distinct positive signals — explicit CFO language, peer-group pattern, activist pressure. Base rate for "any buyback announcement in a given quarter from an eligible large company" is moderate (roughly 25–35%). The specific signals materially lift that. CFO hints and activist pressure are both strong tells. Final estimate: 65% (confidence 65 — the signals are soft-positive, not hard-commit; CFO hints often fail to convert, and activist demands take longer than one quarter).

# Interpreting sparse or off-topic headlines

When headlines don't directly address the question, do not treat absence as evidence against. Markets often resolve based on information that never reaches a headline feed (internal decisions, scheduled events, base-rate outcomes). In those cases, rely on the base rate for the reference class and report a lower confidence (30–50). Do not artificially shift the estimate just because you feel uncertain — uncertainty in your reasoning belongs in the confidence field, not in the probability.

If headlines are contradictory (some supporting, some against), weight by source quality and specificity. A specific factual report ("Senator X filed an amendment doing Y") outweighs a general sentiment piece ("analysts expect Z"). If you cannot reconcile contradictions, keep the estimate closer to the base rate and lower your confidence.

If a headline seems to directly resolve the question (e.g., "Court rules X wins case" when asked "Will X win the case?"), still consider whether the outcome might be reversed, appealed, or re-opened within the market's resolution window. Near-certain resolutions still deserve 95–99% rather than 100%.

# Output format

Reply with ONLY valid JSON — no markdown fences, no preamble, no trailing text. The JSON must contain exactly three fields:
- "implied_probability": a float in [0.01, 0.99]
- "confidence": an integer in [0, 100] — your confidence that your own estimate is well-calibrated
- "reasoning": a short string (under 200 chars) — the key reasoning step that produced the estimate

If the headlines are empty or irrelevant, fall back to the base rate and report a lower confidence (typically 30–50) rather than refusing.
"""


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
# Unified client
# ---------------------------------------------------------------------------


class LLMClient:
    """
    Fallback-chain LLM client.

    Tries providers in configured order, returns first success.
    Falls back to rule-based scoring if all providers fail.

    When cost_ledger is provided, filters paid providers when over budget.
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
        agent_name: str = "unknown",
        cost_ledger: "CostLedger | None" = None,
        notifier: "Notifier | None" = None,
    ) -> None:
        self._chain: list[str] = chain or [
            "anthropic",
            "bedrock",
            "groq",
            "ollama",
            "rule-based",
        ]
        self._agent_name = agent_name
        self._cost_ledger = cost_ledger
        self._notifier = notifier
        self._fired_alerts: set[str] = set()

        self.registry = ProviderRegistry()

        if anthropic_key:
            self.registry.register(
                AnthropicProvider(api_key=anthropic_key, model=anthropic_model)
            )

        if bedrock_region:
            self.registry.register(
                BedrockProvider(
                    region=bedrock_region,
                    model=bedrock_model,
                    access_key_id=bedrock_access_key_id,
                    secret_access_key=bedrock_secret_access_key,
                )
            )

        if groq_key:
            self.registry.register(GroqProvider(api_key=groq_key, model=groq_model))

        self.registry.register(OllamaProvider(base_url=ollama_url, model=ollama_model))

        # Per-provider circuit breaker (disabled after N consecutive failures)
        self._fail_counts: dict[str, int] = {}
        self._disabled: dict[str, bool] = {}
        self._max_fails = 5

        # Per-agent daily LLM cap (cents). Populated at startup from
        # config.llm.agent_budgets via set_agent_budgets(); empty = no caps.
        self._agent_budgets: dict[str, int] = {}
        self._agent_cap_cents: int | None = None

    def set_agent_budgets(self, budgets: dict[str, int]) -> None:
        """Install per-agent daily cap values. Call once at startup."""
        self._agent_budgets = dict(budgets)

    def for_agent(self, agent_name: str) -> "LLMClient":
        """Return a lightweight view that records cost under a different agent name.

        Shares the same registry, chain, circuit breakers, and cost_ledger
        as the parent. Resolves the per-agent cap from ``_agent_budgets`` so
        ``is_over_budget()`` can short-circuit LLM-dependent scans.
        """
        proxy = object.__new__(LLMClient)
        proxy._chain = self._chain
        proxy._agent_name = agent_name
        proxy._cost_ledger = self._cost_ledger
        proxy._notifier = self._notifier
        proxy._fired_alerts = self._fired_alerts
        proxy.registry = self.registry
        proxy._fail_counts = self._fail_counts
        proxy._disabled = self._disabled
        proxy._max_fails = self._max_fails
        proxy._agent_budgets = getattr(self, "_agent_budgets", {})
        proxy._agent_cap_cents = proxy._agent_budgets.get(agent_name)
        return proxy

    async def is_over_budget(self) -> bool:
        """True when this agent has exhausted its per-agent daily LLM cap.

        Call-sites (strategy scan entry points) use this to short-circuit
        LLM-dependent scans when the cap is hit. No cap configured ⇒ False.
        """
        cap = getattr(self, "_agent_cap_cents", None)
        name = getattr(self, "_agent_name", None)
        if cap is None or name is None or self._cost_ledger is None:
            return False
        return not await self._cost_ledger.check_agent_budget(name, cap)

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

    async def _record_cost(self, result: LLMResult) -> None:
        if not self._cost_ledger:
            return
        if result.input_tokens is None and result.output_tokens is None:
            return

        await self._cost_ledger.record(
            self._agent_name,
            result.provider,
            result.model,
            result.input_tokens or 0,
            result.output_tokens or 0,
        )
        await self._maybe_fire_alert()

    async def _maybe_fire_alert(self) -> None:
        event_type = await self._cost_ledger.check_thresholds()
        if not event_type:
            return
        if event_type in self._fired_alerts:
            return
        self._fired_alerts.add(event_type)

        from datetime import datetime, timedelta, timezone

        from notifications.cost import CostAlertData, notify_cost_event

        spend = await self._cost_ledger.get_global_spend()
        budget = self._cost_ledger._config.daily_budget_cents
        (
            top_agent,
            top_spend,
            provider_breakdown,
        ) = await self._cost_ledger.get_breakdown()
        grace_deadline = await self._cost_ledger._get_grace_deadline()

        data = CostAlertData(
            global_spend_cents=spend,
            budget_cents=budget,
            percent_used=(spend / budget * 100) if budget > 0 else 0.0,
            top_agent=top_agent,
            top_agent_spend_cents=top_spend,
            provider_breakdown=provider_breakdown,
            grace_deadline=grace_deadline,
            window_reset_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        await notify_cost_event(event_type, data, self._notifier)

    async def complete(
        self, prompt: str, *, max_tokens: int = 200, temperature: float | None = None
    ) -> LLMResult:
        from llm.stats import get_stats_collector

        providers = await self._resolve_chain()
        collector = get_stats_collector()

        for provider_name in providers:
            if provider_name == "rule-based":
                continue
            if self._is_disabled(provider_name):
                continue

            provider = self.registry.get(provider_name)
            if provider:
                result = await provider.complete(prompt, max_tokens=max_tokens)
                if result:
                    self._record_success(provider_name)
                    collector.record_call(result, success=True)
                    await self._record_cost(result)
                    return result
                else:
                    self._record_failure(provider_name)

        logger.error("LLMClient: all providers failed, returning empty result")
        return LLMResult(text="", provider="anthropic", model="none")

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 500,
    ) -> LLMResult:
        providers = await self._resolve_chain()

        for provider_name in providers:
            if provider_name == "rule-based":
                continue
            if self._is_disabled(provider_name):
                continue

            provider = self.registry.get(provider_name)
            if provider:
                result = await provider.chat(system, messages, max_tokens=max_tokens)
                if result:
                    self._record_success(provider_name)
                    await self._record_cost(result)
                    return result
                else:
                    self._record_failure(provider_name)

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
        providers = await self._resolve_chain()
        for provider_name in providers:
            if provider_name == "rule-based":
                continue
            if self._is_disabled(provider_name):
                continue

            provider = self.registry.get(provider_name)
            if provider:
                result = await provider.complete(prompt)
                if result and result.text:
                    self._record_success(provider_name)
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
                                    max(
                                        -1.0,
                                        min(1.0, data.get("mispricing_score", 0.0)),
                                    )
                                ),
                            )
                    except (json.JSONDecodeError, ValueError):
                        pass
                else:
                    self._record_failure(provider_name)

        # Rule-based fallback — always available
        logger.debug("LLMClient: using rule-based fallback for headline scoring")
        return _rule_based_score_headline(headline)

    async def estimate_probability(
        self,
        question: str,
        headlines: list[str],
        *,
        ensemble_n: int = 3,
    ) -> ProbabilityEstimate:
        """
        Estimate probability from headlines using a Foresight-style
        ensemble of N independent samples, median-averaged for robustness
        to a single miscalibrated draw.

        Within one provider: fire `ensemble_n` parallel calls with the
        same cached system prompt and the same user prompt. The Anthropic
        API returns independent samples because of its default sampling
        temperature. Parse each; take the median probability across
        successful parses. Falls back to the next provider in the chain
        only if zero samples parse successfully (rare — usually means the
        provider itself is down).

        Reference: LightningRod Labs' Foresight-32B (Feb 2026) found that
        sampling N=3 independent probability predictions and aggregating
        closes most of the calibration gap between a base model and a
        fine-tuned forecaster. See PROBABILITY_ESTIMATOR_SYSTEM for the
        calibration guidance this composes with.

        Args:
            question: The binary market question.
            headlines: Recent news headlines to inform the estimate.
            ensemble_n: Number of samples to draw. Default 3 (Foresight
                paper's setting). Set to 1 to disable ensembling.
        """
        import asyncio
        import statistics

        headlines_text = (
            "\n".join(f"- {h}" for h in headlines)
            if headlines
            else "(no recent headlines)"
        )
        # User message is per-call content; the calibration guidance lives in
        # PROBABILITY_ESTIMATOR_SYSTEM and is cached at the Anthropic layer.
        user_prompt = (
            f"Question: {question}\n\n"
            f"Recent headlines:\n{headlines_text}"
        )
        n = max(1, ensemble_n)

        providers = await self._resolve_chain()
        for provider_name in providers:
            if provider_name == "rule-based":
                continue
            if self._is_disabled(provider_name):
                continue

            provider = self.registry.get(provider_name)
            if not provider:
                continue

            # Fire N samples in parallel. Prompt caching (cache_system=True)
            # means only the first call pays full system-token cost; the
            # remaining N-1 hit the cache at 0.1x rate within the 5-min TTL.
            tasks = [
                provider.complete(
                    user_prompt,
                    system=PROBABILITY_ESTIMATOR_SYSTEM,
                    cache_system=True,
                )
                for _ in range(n)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            parsed: list[ProbabilityEstimate] = []
            for result in results:
                if isinstance(result, BaseException) or not result or not result.text:
                    continue
                try:
                    match = re.search(r"\{.*\}", result.text, re.DOTALL)
                    if not match:
                        continue
                    data = json.loads(match.group(0))
                    parsed.append(
                        ProbabilityEstimate(
                            implied_probability=max(
                                0.01,
                                min(0.99, float(data.get("implied_probability", 0.5))),
                            ),
                            confidence=max(
                                0, min(100, int(data.get("confidence", 50)))
                            ),
                            reasoning=str(data.get("reasoning", "")),
                        )
                    )
                except (json.JSONDecodeError, ValueError):
                    continue

            if parsed:
                self._record_success(provider_name)
                probs = [p.implied_probability for p in parsed]
                confs = [p.confidence for p in parsed]
                median_prob = statistics.median(probs)
                mean_conf = int(round(sum(confs) / len(confs)))
                # Reduce confidence when the ensemble disagrees — spread is
                # direct evidence of how calibrated the samples are with
                # each other. Samples within 0.05 of each other are stable.
                if len(probs) >= 2:
                    spread = max(probs) - min(probs)
                    if spread > 0.20:
                        mean_conf = max(0, mean_conf - 25)
                    elif spread > 0.10:
                        mean_conf = max(0, mean_conf - 10)
                reasoning = (
                    parsed[len(parsed) // 2].reasoning
                    if parsed[len(parsed) // 2].reasoning
                    else "; ".join(p.reasoning for p in parsed if p.reasoning)[:200]
                )
                return ProbabilityEstimate(
                    implied_probability=median_prob,
                    confidence=mean_conf,
                    reasoning=reasoning,
                )
            else:
                self._record_failure(provider_name)

        # Rule-based fallback
        logger.debug("LLMClient: using rule-based fallback for probability estimate")
        return _rule_based_probability(question, headlines)

    async def structured_complete(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None:
        """
        Structured output with JSON schema validation.

        Tries Anthropic with native JSON schema support first,
        then falls back to other providers with JSON parsing.

        Returns parsed dict if successful, None if all providers fail.
        """
        import json
        import re

        providers = await self._resolve_chain()

        # Try Anthropic first (has native JSON schema support)
        if "anthropic" in providers and not self._is_disabled("anthropic"):
            provider = self.registry.get("anthropic")
            if provider:
                try:
                    import anthropic
                    import time

                    start = time.monotonic()
                    client = anthropic.AsyncAnthropic(api_key=provider.api_key)
                    messages = [{"role": "user", "content": prompt}]
                    create_kwargs = {
                        "model": provider.model,
                        "max_tokens": max_tokens,
                        "messages": messages,
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": schema,
                        },
                    }
                    if system:
                        create_kwargs["system"] = system

                    response = await client.messages.create(**create_kwargs)
                    latency = (time.monotonic() - start) * 1000

                    # Extract text from response
                    text = ""
                    for block in getattr(response, "content", []):
                        if hasattr(block, "text"):
                            text += block.text

                    if text:
                        self._record_success("anthropic")
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError:
                            pass
                except Exception as exc:
                    logger.warning("Anthropic structured failed: %s", exc)
                    self._record_failure("anthropic")

        # Fallback: try other providers with JSON parsing
        for provider_name in providers:
            if provider_name == "anthropic":
                continue  # Already tried
            if provider_name == "rule-based":
                continue
            if self._is_disabled(provider_name):
                continue

            provider = self.registry.get(provider_name)
            if provider:
                # Build prompt that asks for JSON output
                json_prompt = (
                    f"{prompt}\n\n"
                    f"Respond with ONLY valid JSON matching this schema: {json.dumps(schema.get('schema', {}))}\n"
                    f"Do not include any explanation, just the JSON object."
                )
                if system:
                    json_prompt = f"{system}\n\n{json_prompt}"

                result = await provider.complete(json_prompt, max_tokens=max_tokens)
                if result and result.text:
                    self._record_success(provider_name)
                    try:
                        # Try to extract JSON from response
                        match = re.search(r"\{.*\}", result.text, re.DOTALL)
                        if match:
                            return json.loads(match.group(0))
                    except (json.JSONDecodeError, ValueError):
                        pass
                else:
                    self._record_failure(provider_name)

        logger.error("LLMClient.structured_complete: all providers failed")
        return None

    async def embed(self, text: str) -> list[float]:
        """
        Generate vector embeddings for the given text.
        Currently supports Ollama and Bedrock (Titan).
        """
        providers = await self._resolve_chain()

        # Prefer Ollama for local embeddings if available, then Bedrock
        preferred = ["ollama", "bedrock"]
        for provider_name in preferred:
            if provider_name not in providers or self._is_disabled(provider_name):
                continue

            provider = self.registry.get(provider_name)
            if provider:
                try:
                    return await provider.embed(text)
                except Exception:
                    self._record_failure(provider_name)

        logger.error("LLMClient: no embedding provider available")
        return []

    async def _resolve_chain(self) -> list[str]:
        """Return chain filtered to available providers."""
        chain = list(self._chain)
        if "anthropic" in chain and not self.registry.get("anthropic"):
            chain.remove("anthropic")
        if "bedrock" in chain and not self.registry.get("bedrock"):
            chain.remove("bedrock")
        if "groq" in chain and not self.registry.get("groq"):
            chain.remove("groq")
        if "ollama" in chain and not self.registry.get("ollama"):
            chain.remove("ollama")

        if self._cost_ledger and await self._cost_ledger.should_block_paid():
            chain = [p for p in chain if p in self._cost_ledger._free_providers]

        return chain or ["rule-based"]
