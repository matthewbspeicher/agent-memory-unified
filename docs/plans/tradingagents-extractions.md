# Extractions from TauricResearch/TradingAgents

**Source:** https://github.com/TauricResearch/TradingAgents (Apache 2.0)
**Date:** 2026-05-04
**Status:** Drafts — not implemented

Four separate spikes. Each is independent; they can be sequenced or parallelized.
All four emit `Opportunity` objects into the existing `SignalBus` / `ConsensusRouter`
pipeline — none introduce a new runtime layer.

**Shared plumbing already in place:**
- `agents.base.LLMAgent` (model, system_prompt, structured_call helpers)
- `llm.client.LLMClient` (fallback chain + `CostLedger` budget ceiling)
- `agents.consensus.ConsensusRouter` (weighted vote, regime-aware threshold)
- `learning.trade_reflector.TradeReflector.reflect()` (called after every close)
- `learning.prompt_store.PromptStore.record_lesson()` / `get_runtime_prompt()`
- `agents.config.register_strategy(name, factory)`

**Attribution:** when we land borrowed prompts, prepend a short header linking
to the TradingAgents README and note Apache 2.0.

---

## Draft 1 — `DebateAnalyst` agent (HIGH value, ~1-day spike)

Bull vs. bear rounds → one `Opportunity` with `confidence` derived from
agreement + conviction. This is the one we actually want in production.

**New file:** `trading/strategies/debate_analyst.py`

```python
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from agents.base import LLMAgent
from agents.models import Opportunity, OpportunityStatus
from broker.models import Symbol
from data.bus import DataBus
from llm.client import LLMClient
from strategies.prompts.debate import BULL_SYSTEM, BEAR_SYSTEM, JUDGE_SYSTEM

logger = logging.getLogger(__name__)


class DebateAnalystAgent(LLMAgent):
    """Bull/bear structured debate → single Opportunity per symbol.

    parameters:
        rounds: int = 2                # debate rounds before judging
        max_symbols_per_scan: int = 5  # hard cap — LLM calls are expensive
        min_confidence: float = 0.55   # below this we drop the opportunity
    """

    @property
    def description(self) -> str:
        return f"Bull/bear debate analyst ({self.model}, {self._rounds} rounds)"

    def __init__(self, config, prompt_store=None, llm_client: LLMClient | None = None):
        super().__init__(config, prompt_store=prompt_store)
        p = config.parameters
        self._rounds: int = int(p.get("rounds", 2))
        self._max_symbols: int = int(p.get("max_symbols_per_scan", 5))
        self._min_conf: float = float(p.get("min_confidence", 0.55))
        self._llm = llm_client or LLMClient()

    async def scan(self, data: DataBus) -> list[Opportunity]:
        symbols = data.get_universe(self.config.universe)[: self._max_symbols]
        out: list[Opportunity] = []
        for sym in symbols:
            ctx = await self._build_context_bundle(data, sym)
            decision = await self._run_debate(sym, ctx)
            if decision is None or decision["confidence"] < self._min_conf:
                continue
            out.append(self._to_opportunity(sym, decision, ctx))
            self.increment_llm_call_count()
        return out

    async def _run_debate(self, sym: Symbol, ctx: str) -> dict[str, Any] | None:
        bull_turns: list[str] = []
        bear_turns: list[str] = []
        for _ in range(self._rounds):
            bull = await self._llm.chat(
                system=BULL_SYSTEM,
                messages=self._messages(ctx, bear_turns, bull_turns, side="bull"),
                max_tokens=400,
            )
            bull_turns.append(bull.text)
            bear = await self._llm.chat(
                system=BEAR_SYSTEM,
                messages=self._messages(ctx, bull_turns, bear_turns, side="bear"),
                max_tokens=400,
            )
            bear_turns.append(bear.text)

        return await self._llm.structured_complete(
            prompt=self._judge_prompt(sym, ctx, bull_turns, bear_turns),
            schema=_JUDGE_SCHEMA,
            system=JUDGE_SYSTEM,
        )

    def _to_opportunity(
        self, sym: Symbol, d: dict[str, Any], ctx: str
    ) -> Opportunity:
        return Opportunity(
            id=str(uuid.uuid4()),
            agent_name=self.name,
            symbol=sym,
            signal=d["direction"],  # "long" | "short" | "flat"
            confidence=float(d["confidence"]),
            reasoning=d["reasoning"],
            data={
                "debate_rounds": self._rounds,
                "agreement_score": d.get("agreement", 0.0),
                "bull_strongest": d.get("bull_strongest"),
                "bear_strongest": d.get("bear_strongest"),
                "ctx_digest": ctx[:500],
            },
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

    # … _build_context_bundle, _messages, _judge_prompt elided
```

**Confidence model (the one design call that matters):**

```
agreement   = 1 - jensen_shannon(bull_prob_dist, bear_prob_dist)  # 0-1
conviction  = |judge.target_probability - 0.5| * 2                # 0-1
confidence  = 0.6 * conviction + 0.4 * (1 - agreement)
```

Low agreement + strong conviction = high signal. Unanimous "both bullish" is
noise (both agents told the same story), not signal — penalized.

**Wire-up:**
1. `agents/config.py::_ensure_strategies_registered` — add
   `register_strategy("debate_analyst", DebateAnalystAgent)`.
2. `agents.yaml` sample:
   ```yaml
   - name: debate_nvda
     strategy: debate_analyst
     schedule: cron
     cron: "0 14 * * 1-5"       # once a day, mid-session
     action_level: notify         # start in notify; promote after eval
     universe: ["NVDA", "MSFT", "AAPL"]
     parameters:
       rounds: 2
       max_symbols_per_scan: 3
       min_confidence: 0.6
   ```
3. `ConsensusRouter` needs no change — `DebateAnalystAgent` is just another
   voter. Set its weight via the existing `AgentWeightProfile` path once we
   have 20+ realized trades.
4. `trading/strategies/prompts/debate.py` — lift bull/bear/judge prompt
   skeletons from TradingAgents, strip LangGraph-specific bits, adapt to
   our `Opportunity` schema. Attribute Apache 2.0 in the file header.

**Tests to write** (`tests/unit/test_strategies/test_debate_analyst.py`):
- Scan with `LLMClient` stub returning canned bull/bear/judge → one `Opportunity`.
- `min_confidence` filter drops low-conviction results.
- Timeout on `_run_debate` does not crash the scan (returns empty list).
- Kill switch raised → `scan_with_guards` short-circuits.

**Cost guardrail:** a 3-symbol × 2-round scan = 3 × (2 + 2 + 1) = 15 LLM calls.
At Sonnet ~0.3¢/call that's ~5¢/scan. Once-daily cron → ~$1/mo per dashboard
symbol. Cap via `max_symbols_per_scan` and the existing `CostLedger`.

---

## Draft 2 — Role-specialized analyst prompts (LOW risk, prompt-only)

Not a new agent — lift their four analyst prompts and slot them into
`PromptStore` so any existing `LLMAgent` can opt in by `strategy` name.

**New file:** `trading/strategies/prompts/analysts.py`

```python
"""Analyst role prompts, adapted from TradingAgents (Apache 2.0).

Each prompt expects a context bundle with {ticker, asof_iso, data_summary,
recent_lessons}. Returns JSON matching ANALYST_SCHEMA for structured_complete.
"""

FUNDAMENTALS_ANALYST = """You are a fundamentals analyst. …"""
SENTIMENT_ANALYST    = """You are a sentiment analyst. …"""
NEWS_ANALYST         = """You are a macro news analyst. …"""
TECHNICAL_ANALYST    = """You are a technical analyst. …"""

ANALYST_SCHEMA = {
    "type": "object",
    "required": ["signal", "confidence", "reasoning", "key_risks"],
    "properties": {
        "signal": {"enum": ["long", "short", "flat"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string", "maxLength": 800},
        "key_risks": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
    },
}
```

**Seed the prompts into the store** (one-time migration):

```python
# trading/scripts/seed_analyst_prompts.py
import asyncio
from learning.prompt_store import PromptStore
from strategies.prompts.analysts import (
    FUNDAMENTALS_ANALYST, SENTIMENT_ANALYST,
    NEWS_ANALYST, TECHNICAL_ANALYST,
)

async def main():
    store = await PromptStore.open()
    for role, body in [
        ("fundamentals", FUNDAMENTALS_ANALYST),
        ("sentiment",    SENTIMENT_ANALYST),
        ("news",         NEWS_ANALYST),
        ("technical",    TECHNICAL_ANALYST),
    ]:
        await store.put_runtime_prompt(f"analyst.{role}", body, version="v1")
```

**Consumer pattern** — existing agents can reach in via
`self._prompt_store.get_runtime_prompt("analyst.technical")` in their scan
method when the agent's `config.parameters.analyst_role` is set.
No new registry entry, no new factory, no new test harness.

**Why this is separately worth doing:**
- Sharpens the `LLMAnalystAgent` we already ship — today its prompt is
  `"You are a market analyst. Analyze the data..."` (see
  `strategies/llm_analyst.py:48`). That's the generic prompt the authors
  of TradingAgents explicitly argued against.
- Enables Draft 1 to consume four specialist views as debate context
  without duplicating prompt text.
- Under 200 lines of code. Zero risk.

---

## Draft 3 — Reflection-on-realized-returns loop (MEDIUM value, tightens existing)

Not a new component — a prompt audit + one new deep-reflection pass.
Goal: match TradingAgents' "what did I miss, update prior" framing inside
our existing `TradeReflector._reflect_deep` path.

**Files to modify:**
1. `trading/learning/trade_reflector.py::_reflect_deep` — currently calls
   the LLM with a terse prompt. Replace the prompt with the template below.
2. `trading/strategies/prompts/reflection.py` — new file, holds the prompt.

**Prompt template** (adapted):

```python
# trading/strategies/prompts/reflection.py
REFLECTION_SYSTEM = """You review closed trades to produce one short
lesson the agent should carry forward.

A good lesson is:
- specific (names the feature, not "the market")
- falsifiable (makes a prediction a future scan could verify)
- calibrated (if the trade lost because confidence was overestimated, say so)

A bad lesson is:
- hindsight ("I should have exited earlier")
- vague ("be more careful with volatility")
- generic ("watch the news")
"""

REFLECTION_USER_TEMPLATE = """Closed trade
-------------
agent:          {agent_name}
symbol:         {symbol}
entry_ts:       {entry_ts}
exit_ts:        {exit_ts}
signal:         {signal}        (what the agent predicted)
realized_pnl:   {pnl:+.2f}      (USD)
outcome:        {outcome}       (win | loss | neutral)
expected_pnl:   {expected:+.2f} (what the agent projected at entry)
surprise_ratio: {surprise:.2f}  (|realized - expected| / max(|expected|, 1))

Original reasoning at entry
---------------------------
{reasoning}

Market context at entry
-----------------------
{ctx_at_entry}

Market context at exit
----------------------
{ctx_at_exit}

Task
----
1. Name the single biggest belief at entry that turned out wrong (or right
   for the wrong reason). Quote or paraphrase it.
2. State the one feature of the market context the agent should weigh more
   heavily next time.
3. Write a one-sentence lesson starting with "When X, prefer Y."
4. Assign a category: calibration | regime | feature | risk | timing.

Return strict JSON:
{{"belief": "...", "feature": "...", "lesson": "...", "category": "..."}}
"""
```

**Integration point** — `TradeReflector._reflect_deep` already calls
`self._llm.structured_complete(...)`. Swap in the new prompt and add the
two-context diff (entry vs. exit). The lesson then flows through the
existing `PromptStore.record_lesson(...)` path into every future system
prompt via `LLMAgent.system_prompt`.

**What actually changes observably:**
- Lessons become shorter and more specific (fewer "be careful" entries).
- Category tag is new — lets us filter in `PromptStore.get_lessons(...)`.
- Surprise ratio is new — separates "predicted correctly, won" from
  "predicted incorrectly, won anyway" (the second shouldn't reinforce
  the agent's prior).

**Tests:** `tests/unit/test_learning/test_trade_reflector.py`
- Stub LLM returning well-formed JSON → lesson written with correct category.
- Stub returning malformed JSON → `_reflect_deep` swallows the error, logs
  warning, does not retry.
- Win-by-accident trade (large `surprise_ratio`, positive pnl) still triggers
  deep reflection — regression test for current loss-only path.

**Risk:** low. Prompt swap + one new JSON field. `_reflect_lightweight`
path (the hot path) is untouched.

---

## Draft 4 — LangGraph checkpoint resume evaluation (SKIP for now — recorded for completeness)

TradingAgents uses LangGraph so their long debate graph can resume after a
crash. Our scans are short (seconds, not minutes) and stateless — we don't
need checkpointing today.

**Revisit trigger:** if Draft 1 evolves into a multi-hour deliberation
(e.g., tool-using ReAct loops with web fetches, IBKR queries, memory
searches) where re-running from zero costs real money or time.

**If we ever adopt it, minimal sketch:**

```python
# trading/agents/checkpointing.py (NOT to be built yet)
class AgentCheckpointer:
    """SQLite-backed checkpoint store for long-running agent scans.

    Writes state after each LLM turn; AgentRunner can resume on crash.
    Keyed by (agent_name, scan_id, turn_index).
    """
    async def save(self, agent_name: str, scan_id: str, turn: int, state: dict) -> None: ...
    async def load(self, agent_name: str, scan_id: str) -> tuple[int, dict] | None: ...
    async def clear(self, agent_name: str, scan_id: str) -> None: ...
```

Hook point would be `AgentRunner._execute_scan` (trading/agents/runner.py:266)
— wrap the call, persist after each LLM turn, clear on success.

**Explicit non-goals:**
- Not adopting LangGraph itself. Our scheduler + SignalBus is simpler and
  Bittensor-aware; LangGraph adds a dependency with no corresponding win.
- Not persisting every rule-based scan. The budget doesn't justify it.

**Decision:** don't build. Re-open this draft when/if Draft 1's scan
duration exceeds ~2 minutes in production.

---

## Suggested sequence

1. **Draft 2** first (prompt seeds, zero risk) — lands in an afternoon,
   immediately sharpens the existing `LLMAnalystAgent`.
2. **Draft 3** next (reflection prompt swap) — one day, improves signal
   quality of every downstream LLM agent.
3. **Draft 1** after (`DebateAnalyst`) — one-day spike, in `notify` mode
   for 2-3 weeks of shadow eval before promoting to `suggest_trade`.
4. **Draft 4** only if Draft 1 grows teeth that need checkpointing.

## Attribution header to use on lifted prompts

```python
# Portions adapted from TradingAgents by TauricResearch
# https://github.com/TauricResearch/TradingAgents
# Licensed under Apache License 2.0
```
