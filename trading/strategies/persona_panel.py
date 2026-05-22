"""PersonaPanelAgent — N investor personas → judge → one Opportunity.

Sibling to ``DebateAnalystAgent``.  Where the debate runs an adversarial
bull-vs-bear back-and-forth, the panel collects ONE independent opinion
per persona (Buffett, Graham, Lynch, Munger, Klarman, Marks) and feeds
them all at once to a judge for synthesis.

Pipeline per symbol:
    parallel(persona → opinion) → judge(opinions, data) → Opportunity

Reuses ``DEBATE`` confidence-blend semantics: confidence is
``conviction × w + (1 - agreement) × (1 - w)`` so a unanimous panel is
penalised as likely already priced.

Persona prompts live in ``strategies.prompts.personas`` (see ADR-0011
section follow-ups and CONTEXT.md for vocabulary).  Judge prompt + schema
live in ``strategies.prompts.panel``.
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
from strategies.prompts.analysts import ANALYST_SCHEMA
from strategies.prompts.panel import (
    PANEL_JUDGE_SYSTEM,
    PANEL_VERDICT_SCHEMA,
    build_panel_judge_prompt,
    build_panelist_user_message,
)
from strategies.prompts.personas import PERSONA_PROMPTS

logger = logging.getLogger(__name__)

# All six persona keys, used when parameters.personas is unset.
DEFAULT_PANEL: list[str] = [
    "buffett_value",
    "graham_deep_value",
    "lynch_growth",
    "munger_quality",
    "klarman_distressed",
    "marks_macro",
]


class PersonaPanelAgent(LLMAgent):
    """N investor-persona panelists + one judge per symbol.

    Parameters (all optional):
        personas: list[str] = DEFAULT_PANEL
            # Keys from strategies.prompts.personas.PERSONA_PROMPTS.
        max_symbols_per_scan: int = 3
            # Hard cap — N personas × M symbols × judge gets expensive fast.
        min_confidence: float = 0.55
        max_tokens_per_panelist: int = 350
        judge_max_tokens: int = 700
        conviction_weight: float = 0.6
            # Same blend as DebateAnalystAgent.
    """

    def __init__(
        self,
        config: AgentConfig,
        prompt_store: Any = None,
        llm_client: Any = None,
    ) -> None:
        super().__init__(config, prompt_store=prompt_store)
        p = config.parameters or {}
        configured = p.get("personas") or DEFAULT_PANEL
        # Filter out unknown personas with a warning rather than crashing —
        # an in-flight rename of a persona shouldn't break the agent.
        self._personas: list[str] = []
        for key in configured:
            if key in PERSONA_PROMPTS:
                self._personas.append(key)
            else:
                logger.warning(
                    "PersonaPanel %s: unknown persona %r, skipping. "
                    "Known: %s",
                    config.name,
                    key,
                    sorted(PERSONA_PROMPTS),
                )
        if not self._personas:
            # Empty panel is a config error; fail loud.
            raise ValueError(
                f"PersonaPanel {config.name}: no valid personas configured. "
                f"Got {configured!r}, known: {sorted(PERSONA_PROMPTS)}"
            )
        self._max_symbols: int = int(p.get("max_symbols_per_scan", 3))
        self._min_conf: float = float(p.get("min_confidence", 0.55))
        self._panelist_tokens: int = int(p.get("max_tokens_per_panelist", 350))
        self._judge_tokens: int = int(p.get("judge_max_tokens", 700))
        self._conviction_weight: float = float(p.get("conviction_weight", 0.6))
        self._llm = llm_client  # lazy LLMClient() if None

    @property
    def description(self) -> str:
        return (
            f"Persona panel ({self.model}, {len(self._personas)} personas, "
            f"up to {self._max_symbols} symbols/scan)"
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
                logger.warning(
                    "PersonaPanel %s: context build failed for %s: %s",
                    self.name,
                    sym.ticker,
                    exc,
                )
                continue

            verdict = await self._run_panel(sym, ctx)
            if verdict is None:
                continue

            confidence = self._blend_confidence(verdict)
            if confidence < self._min_conf or verdict["direction"] == "flat":
                logger.info(
                    "PersonaPanel %s: %s skipped (direction=%s confidence=%.2f < %.2f)",
                    self.name,
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
        """Compact LLM-friendly market summary. Mirrors DebateAnalystAgent."""
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

    async def _gather_opinion(
        self,
        persona_key: str,
        ticker: str,
        asof: str,
        ctx: str,
    ) -> dict | None:
        """Run one panelist; return their structured opinion or None."""
        self.increment_llm_call_count()
        system = PERSONA_PROMPTS[persona_key]
        user = build_panelist_user_message(
            ticker=ticker, asof_iso=asof, data_summary=ctx
        )
        try:
            opinion = await self._llm.structured_complete(
                prompt=user,
                schema=ANALYST_SCHEMA,
                system=system,
                max_tokens=self._panelist_tokens,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "PersonaPanel %s: panelist %s failed for %s: %s",
                self.name,
                persona_key,
                ticker,
                exc,
            )
            return None
        if not opinion or "signal" not in opinion:
            return None
        # Stamp the persona key onto the opinion so the judge can cite it.
        return {"persona": persona_key, **opinion}

    async def _run_panel(self, sym: Symbol, ctx: str) -> dict[str, Any] | None:
        """Run all panelists concurrently, then the judge."""
        asof = datetime.now(timezone.utc).isoformat()

        results = await asyncio.gather(
            *(
                self._gather_opinion(p, sym.ticker, asof, ctx)
                for p in self._personas
            ),
            return_exceptions=False,
        )
        opinions = [o for o in results if o is not None]

        # If less than half the panel produced anything, abort — the data
        # bundle was probably bad and the judge can't synthesize signal
        # from one or two reads.
        if len(opinions) < max(2, len(self._personas) // 2):
            logger.warning(
                "PersonaPanel %s: only %d/%d panelists produced opinions for %s; aborting",
                self.name,
                len(opinions),
                len(self._personas),
                sym.ticker,
            )
            return None

        self.increment_llm_call_count()
        prompt = build_panel_judge_prompt(
            ticker=sym.ticker,
            asof_iso=asof,
            data_summary=ctx,
            opinions=opinions,
        )
        try:
            verdict = await self._llm.structured_complete(
                prompt=prompt,
                schema=PANEL_VERDICT_SCHEMA,
                system=PANEL_JUDGE_SYSTEM,
                max_tokens=self._judge_tokens,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "PersonaPanel %s: judge call failed for %s: %s",
                self.name,
                sym.ticker,
                exc,
            )
            return None
        if not verdict or "direction" not in verdict:
            logger.warning(
                "PersonaPanel %s: judge returned no usable verdict for %s",
                self.name,
                sym.ticker,
            )
            return None

        verdict["_opinions"] = opinions
        return verdict

    def _blend_confidence(self, verdict: dict[str, Any]) -> float:
        """Same blend as DebateAnalystAgent (intentional parity)."""
        try:
            p = float(verdict.get("target_probability", 0.5))
            agreement = float(verdict.get("agreement", 0.5))
        except (TypeError, ValueError):
            return 0.0
        p = max(0.0, min(1.0, p))
        agreement = max(0.0, min(1.0, agreement))
        conviction = abs(p - 0.5) * 2
        return (
            self._conviction_weight * conviction
            + (1 - self._conviction_weight) * (1 - agreement)
        )

    def _to_opportunity(
        self,
        sym: Symbol,
        verdict: dict[str, Any],
        confidence: float,
        ctx: str,
    ) -> Opportunity:
        now = datetime.now(timezone.utc)
        direction = verdict["direction"]
        signal = "PANEL_LONG" if direction == "long" else "PANEL_SHORT"
        reasoning = (verdict.get("reasoning") or "").strip()[:800]
        opinions = verdict.get("_opinions") or []
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
                "majority_personas": verdict.get("majority_personas") or [],
                "dissenting_personas": verdict.get("dissenting_personas") or [],
                "panelist_count": len(opinions),
                "panelist_signals": [
                    {"persona": o.get("persona"), "signal": o.get("signal")}
                    for o in opinions
                ],
                "ctx_digest": ctx[:500],
            },
            timestamp=now,
            status=OpportunityStatus.PENDING,
            expires_at=now + timedelta(minutes=30),
        )
