# CONTEXT.md — Domain vocabulary

Shared language for the `agent-memory-unified` codebase. Created lazily 2026-05-22 as part of ADR-0011. Update inline when new concepts crystallize during architecture or feature work.

Companion to `docs/adr/` (decisions) and `~/.claude/skills/improve-codebase-architecture/LANGUAGE.md` (architecture vocabulary like Module, Seam, Depth).

---

## Trading domain

**Opportunity** — A `dataclass` emitted by an `Agent.scan()` proposing a single trade decision (buy/sell/hold + symbol + confidence + reasoning + optional suggested order). Lives in `agents/models.py`. The atomic unit downstream of every strategy. Compare *Signal*, which is broadcast on the bus and may inform many agents; an Opportunity is the agent's own externalized decision.

**Signal** — Untyped term in casual conversation; in code it means `AgentSignal` (typed payload + `signal_type` + `source_agent` + TTL) flowing through the `SignalBus`. Strategies publish Opportunities; the SignalBus carries inter-agent Signals.

**SignalBus topic** — Convention: each `signal_type` registered in `data/signal_types.py` is a "topic." Subscribers receive every published signal; queries filter by topic. Topics are typed via Pydantic models registered in `SignalTypeRegistry`. Adding a new topic is a deliberate decision (see ADR-0011 for the most recent addition, `intel_sentiment`).

**Strategy** — A class under `trading/strategies/` implementing the `Agent` ABC. The implementation half of a deployed agent. Compare *Agent*, which is the configured-and-named instance.

**Agent** — An *instance* of a strategy: a YAML entry under `trading/agents.yaml` or `trading/agents.paper.yaml` that binds a strategy to a name, schedule, universe, parameters, and trust level. The same strategy can back many agents (e.g. `kalshi_news_arb` and `polymarket_news_arb` strategies have one agent each today, but the strategy class is reusable).

**Persona** — A specialization of the `llm_analyst` (or future `react_analyst`) strategy where the YAML `system_prompt` shapes the agent's lens. Six are planned for `agents.paper.yaml`: Buffett (value), Graham (deep value), Lynch (growth), Munger (quality), Klarman (distressed), Marks (macro contrarian). Personas remain in `agents.paper.yaml` until they satisfy the ADR-0010 graduation gate.

**Trust level** — One of `monitored`, `assisted`, `autonomous`. Set per-agent in YAML. Drives router behavior in `agents/router.py`: monitored agents emit Opportunities for review; autonomous agents can route to the broker without human approval.

**Action level** — One of `notify`, `suggest_trade`, `auto_execute`. Independent of trust level; specifies what the agent is *allowed* to do with its Opportunity.

## Intelligence domain

**IntelReport** — Normalized output from any `intelligence/providers/*` module: `(source, symbol, score [-1..1], confidence [0..1], veto, details)`. Consumed by `enrich_confidence()` to adjust the confidence on `bittensor_consensus` signals and (per ADR-0011) published as the `intel_sentiment` topic for sentiment-source reports.

**Veto** — A boolean on `IntelReport` that, when true, signals a hard block on the enriched-consensus signal. Vetoes short-circuit normal enrichment but, post-ADR-0011, do NOT block per-provider topic publishing for non-vetoed reports.

**Sentiment** (normalized) — The aggregate score `IntelligenceLayer` produces from Fear & Greed + LunarCrush + AV AI sentiment. A single number per symbol with a confidence band. Distinct from *sentiment_spike*, which is a discrete event signal fired only on social-sentiment bursts.

## Bittensor domain

**TaoshiBridge** — The polling adapter (`integrations/bittensor/taoshi_bridge.py`) that watches the official Taoshi validator's position files and republishes them as `bittensor_miner_position` signals. See ADR-0007.

**Consensus** — The aggregated directional vote across Subnet 8 miners for a (symbol, timeframe). Published as `bittensor_consensus`; the `IntelligenceLayer` enriches it into `intel_enriched_consensus`.

## Architecture (project-specific overlays on LANGUAGE.md)

**Two-process architecture** — Per ADR-0007: the trading engine (this repo's `bittensor>=10`) and the official Taoshi validator (`taoshi-vanta/`, `bittensor==9.12.1`) run as separate venvs; the bridge is the only point of contact.

**Graduation gate** — Per ADR-0010: paper → live promotion requires backtest + paper + ops + review evidence. Personas (and any new strategy) enter via `agents.paper.yaml`.

**Scope** — Agent identity authorization unit (see `trading/api/identity/`). One of `write:orders`, `risk:halt`, `control:agents`, `admin`. New write endpoints use `require_scope(...)`, not the legacy `verify_api_key`.
