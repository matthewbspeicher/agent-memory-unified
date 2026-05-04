"""DebateAnalyst — bull vs. bear structured debate collapsed to one Opportunity.

Portions adapted from TradingAgents by TauricResearch
https://github.com/TauricResearch/TradingAgents
Licensed under Apache License 2.0.

Pipeline per symbol:
    bull turn 1 → bear turn 1 → … (N rounds) → judge(structured) → Opportunity

Confidence combines the judge's conviction (|p - 0.5| * 2) with the debate's
disagreement (1 - agreement). Unanimous debates are treated as noise: if both
sides told the same story, the market likely has priced it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from agents.base import LLMAgent
from agents.models import AgentConfig, Opportunity, OpportunityStatus
from broker.models import Symbol
from data.bus import DataBus
from strategies.prompts.debate import (
    BEAR_SYSTEM,
    BULL_SYSTEM,
    DEBATE_VERDICT_SCHEMA,
    JUDGE_SYSTEM,
    build_judge_prompt,
)

logger = logging.getLogger(__name__)


class DebateAnalystAgent(LLMAgent):
    """Emit one `Opportunity` per debated symbol via bull/bear/judge pipeline.

    Parameters (all optional, with defaults):
        rounds: int = 2                  # debate rounds before judging
        max_symbols_per_scan: int = 3    # hard cap on LLM spend per scan
        min_confidence: float = 0.55     # drop opportunities below this floor
        max_tokens_per_turn: int = 400
        judge_max_tokens: int = 700
        conviction_weight: float = 0.6   # weighting in confidence blend
    """

    def __init__(
        self,
        config: AgentConfig,
        prompt_store: Any = None,
        llm_client: Any = None,
    ) -> None:
        super().__init__(config, prompt_store=prompt_store)
        p = config.parameters or {}
        self._rounds: int = int(p.get("rounds", 2))
        self._max_symbols: int = int(p.get("max_symbols_per_scan", 3))
        self._min_conf: float = float(p.get("min_confidence", 0.55))
        self._turn_tokens: int = int(p.get("max_tokens_per_turn", 400))
        self._judge_tokens: int = int(p.get("judge_max_tokens", 700))
        self._conviction_weight: float = float(p.get("conviction_weight", 0.6))
        self._llm = llm_client  # lazily initialized below if None

    @property
    def description(self) -> str:
        return (
            f"Bull/bear debate analyst ({self.model}, "
            f"{self._rounds} rounds, up to {self._max_symbols} symbols/scan)"
        )

    async def scan(self, data: DataBus) -> list[Opportunity]:
        if self._llm is None:
            from llm.client import LLMClient

            self._llm = LLMClient()

        universe = data.get_universe(self.config.universe)
        symbols = list(universe)[: self._max_symbols]
        opps: list[Opportunity] = []
        for sym in symbols:
            try:
                ctx = await self._build_context_bundle(data, sym)
            except Exception as exc:
                logger.warning("DebateAnalyst: context build failed for %s: %s", sym.ticker, exc)
                continue

            verdict = await self._run_debate(sym, ctx)
            if verdict is None:
                continue

            confidence = self._blend_confidence(verdict)
            if confidence < self._min_conf or verdict["direction"] == "flat":
                logger.info(
                    "DebateAnalyst: %s skipped (direction=%s confidence=%.2f < %.2f)",
                    sym.ticker,
                    verdict["direction"],
                    confidence,
                    self._min_conf,
                )
                continue

            opps.append(self._to_opportunity(sym, verdict, confidence, ctx))

        return opps

    # ------------------------------------------------------------------ internals

    async def _build_context_bundle(self, data: DataBus, sym: Symbol) -> str:
        """Compact, LLM-friendly summary of the symbol's current state.

        Keeps the prompt under ~1KB per symbol. All three get_* calls here
        have try/except in the DataBus, so missing fields degrade gracefully.
        """
        summary = await data.get_market_summary(sym)
        levels: dict = {}
        vol: dict = {}
        try:
            levels = await data.get_key_levels(sym, timeframe="1d")
        except Exception:
            pass
        try:
            vol = await data.get_volatility_summary(sym)
        except Exception:
            pass

        bundle = {
            "market": summary,
            "levels": levels,
            "volatility": vol,
        }
        return json.dumps(bundle, default=str, indent=2)

    async def _run_debate(self, sym: Symbol, ctx: str) -> dict[str, Any] | None:
        """Run N rounds of bull/bear, then judge. Returns parsed verdict or None."""
        asof = datetime.now(timezone.utc).isoformat()
        header = f"# Ticker\n{sym.ticker}\n\n# As of (UTC)\n{asof}\n\n# Data bundle\n{ctx}"

        bull_turns: list[str] = []
        bear_turns: list[str] = []

        for round_idx in range(self._rounds):
            self.increment_llm_call_count()
            bull_msg = self._build_side_messages(header, bear_turns, bull_turns, side="bull")
            bull_res = await self._llm.chat(
                system=BULL_SYSTEM,
                messages=bull_msg,
                max_tokens=self._turn_tokens,
            )
            bull_text = (getattr(bull_res, "text", "") or "").strip()
            if not bull_text:
                logger.warning("DebateAnalyst: empty bull turn for %s round %d", sym.ticker, round_idx)
                return None
            bull_turns.append(bull_text)

            self.increment_llm_call_count()
            bear_msg = self._build_side_messages(header, bull_turns, bear_turns, side="bear")
            bear_res = await self._llm.chat(
                system=BEAR_SYSTEM,
                messages=bear_msg,
                max_tokens=self._turn_tokens,
            )
            bear_text = (getattr(bear_res, "text", "") or "").strip()
            if not bear_text:
                logger.warning("DebateAnalyst: empty bear turn for %s round %d", sym.ticker, round_idx)
                return None
            bear_turns.append(bear_text)

        self.increment_llm_call_count()
        prompt = build_judge_prompt(
            ticker=sym.ticker,
            asof_iso=asof,
            data_summary=ctx,
            bull_turns=bull_turns,
            bear_turns=bear_turns,
        )
        try:
            verdict = await self._llm.structured_complete(
                prompt=prompt,
                schema=DEBATE_VERDICT_SCHEMA,
                system=JUDGE_SYSTEM,
                max_tokens=self._judge_tokens,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("DebateAnalyst: judge call failed for %s: %s", sym.ticker, exc)
            return None

        if not verdict or "direction" not in verdict:
            logger.warning("DebateAnalyst: judge returned no usable verdict for %s", sym.ticker)
            return None

        verdict["_bull_turns"] = bull_turns
        verdict["_bear_turns"] = bear_turns
        return verdict

    @staticmethod
    def _build_side_messages(
        header: str,
        opponent_turns: list[str],
        own_turns: list[str],
        *,
        side: str,
    ) -> list[dict[str, str]]:
        """Build a chat history alternating opponent / self turns."""
        messages: list[dict[str, str]] = [{"role": "user", "content": header}]
        for i, opp in enumerate(opponent_turns):
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Opponent ({'bear' if side == 'bull' else 'bull'}) "
                        f"argument, round {i + 1}:\n{opp}"
                    ),
                }
            )
            if i < len(own_turns):
                messages.append({"role": "assistant", "content": own_turns[i]})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Deliver your round {len(own_turns) + 1} {side} argument. "
                    "Engage with the opponent's most recent points by name. "
                    "Keep it under 200 words."
                ),
            }
        )
        return messages

    def _blend_confidence(self, verdict: dict[str, Any]) -> float:
        """confidence = w * conviction + (1-w) * (1 - agreement).

        Low agreement + strong conviction = high signal.
        Unanimous agreement is penalized as likely already priced.
        """
        try:
            p = float(verdict.get("target_probability", 0.5))
            agreement = float(verdict.get("agreement", 0.5))
        except (TypeError, ValueError):
            return 0.0
        p = max(0.0, min(1.0, p))
        agreement = max(0.0, min(1.0, agreement))
        conviction = abs(p - 0.5) * 2
        return self._conviction_weight * conviction + (1 - self._conviction_weight) * (1 - agreement)

    def _to_opportunity(
        self,
        sym: Symbol,
        verdict: dict[str, Any],
        confidence: float,
        ctx: str,
    ) -> Opportunity:
        now = datetime.now(timezone.utc)
        direction = verdict["direction"]
        signal = "DEBATE_LONG" if direction == "long" else "DEBATE_SHORT"
        reasoning = (verdict.get("reasoning") or "").strip()[:800]
        return Opportunity(
            id=str(uuid.uuid4()),
            agent_name=self.name,
            symbol=sym,
            signal=signal,
            confidence=round(confidence, 4),
            reasoning=reasoning,
            data={
                "direction": direction,
                "target_probability": float(verdict.get("target_probability", 0.5)),
                "agreement": float(verdict.get("agreement", 0.5)),
                "bull_strongest": verdict.get("bull_strongest", ""),
                "bear_strongest": verdict.get("bear_strongest", ""),
                "debate_rounds": self._rounds,
                "ctx_digest": ctx[:500],
            },
            timestamp=now,
            status=OpportunityStatus.PENDING,
            expires_at=now + timedelta(minutes=30),
        )
