# go-trader Incorporation — Merged Roadmap

**Date**: 2026-04-10
**Status**: APPROVED (plan mode)
**Supersedes / extends**: [`go-trader-incorporation-plan.md`](./go-trader-incorporation-plan.md) (the OpenCode 8-feature plan — kept as reference for its inline code snippets)
**Relationship**: This document is the merged roadmap that combines the agent's own research on [`richkuo/go-trader`](https://github.com/richkuo/go-trader) with the OpenCode plan. OpenCode's plan contributed the consecutive-loss breaker, fee/slippage models, and agent concurrency caps (three gaps the agent missed). This document contributes the options Greeks engine, new strategy agents (Triple EMA, pairs spread), multi-venue shadow mode, and the frontend dashboard wrap-up that OpenCode omitted. Treat this roadmap as the canonical phased plan; read `go-trader-incorporation-plan.md` alongside it when you need the concrete code-snippet form of Phases 1, 2, 4, and 6.

---

## Context

**Why this change.** The user asked whether we could learn from [`richkuo/go-trader`](https://github.com/richkuo/go-trader), a Go+Python hybrid trading bot covering spot / options / perps / futures / crypto across seven exchanges with ~50 strategies. Our `agent-memory-unified` trading engine is broader and more sophisticated in several areas (consensus weighting, Postgres-backed state, Bittensor, memory), but research (augmented by an OpenCode plan the user shared) surfaced eight concrete gaps where go-trader's patterns would harden our system. This plan lays out a phased roadmap to incorporate all of them.

**Research summary.**

- **Go-trader's strengths.** (1) Per-strategy drawdown circuit breakers with explicit 5–10% thresholds and a 25% portfolio-level kill switch. (2) Consecutive-loss circuit breakers (halt after N losing trades, orthogonal to drawdown). (3) Concentration monitoring — flags when a single asset exceeds 60% of portfolio exposure or when >75% of strategies align directionally. (4) Options "Greek balancing" that scores candidate trades against existing position Greeks and a theta harvester that closes sold options at 60% profit / 200% loss / 3 DTE. (5) Per-exchange fee and slippage models that flow into position sizing and expected-value calculations. (6) Per-strategy higher-timeframe (HTF) trend filter. (7) Agent concurrency caps at the scheduler level. (8) 50+ named strategies including Triple EMA confluence and pairs-spread stat arb.

- **Input sources.** This plan merges the agent's own research with an OpenCode plan the user shared. OpenCode's plan flagged three items I had missed (consecutive-loss breaker, fee/slippage models, concurrency limits) and they have been folded in. OpenCode omitted the heavier options-Greeks engine, the dashboard wrap-up, and the new-strategy work; those are retained from the original roadmap so the final plan covers both scopes.
- **What we already have and will reuse.** The ground we don't need to retread:
  - `trading/risk/analytics.py` — drawdown, VaR, CVaR, leverage, per-symbol risk (lines 25–96)
  - `trading/risk/circuit_breaker.py` — full state machine CLOSED → OPEN → HALF_OPEN (lines 20–207); currently wired only to risk-data providers
  - `trading/risk/kill_switch.py` — on/off with reason (lines 4–27); no threshold trigger yet
  - `trading/risk/governor.py` — `DrawdownWatchdog` (lines 85–100+) that demotes trust levels, `CapitalAllocator`, correlation guard
  - `trading/risk/correlation.py` — `pearson_correlation`, `avg_portfolio_correlation`
  - `trading/learning/correlation_monitor.py` — rolling agent P&L correlation tracker with NORMAL/WARNING/CRITICAL alerts and cooldowns
  - `trading/data/indicators.py` — SMA, EMA, RSI, MACD, Bollinger, ATR, realized vol, VWAP, `pandas_ta` integration
  - `trading/data/bus.py` — `DataBus.get_historical(symbol, timeframe, lookback_days)` with TTL cache
  - `trading/data/signal_bus.py` — in-memory pub/sub (lines 12–64)
  - `trading/agents/base.py` — `Agent`, `StructuredAgent`, `LLMAgent` (lines 13–149)
  - `trading/agents/consensus.py` — weighting (EQUAL / CONFIDENCE / SHARPE / ELO / COMPOSITE)
  - `trading/agents/router.py` — `OpportunityRouter` (lines 54–147) with shadow-mode hook
  - `trading/notifications/` — Discord / Slack / WhatsApp / composite notifiers
  - `trading/backtesting/engine.py` — `BacktestEngine` with walk-forward, equity curve, commission models
  - `trading/strategies/options_hedging.py` — `OptionsHedgingAgent` (iron condor / collar / protective put) — currently has no Greek scoring
  - `trading/adapters/ibkr/adapter.py` — full options chain support
  - `trading/data/sources/broker_source.py` — `supports_options` / `get_options_chain`
- **What's genuinely missing.**
  - Circuit breakers are not wired per-agent in `OpportunityRouter`; `DrawdownWatchdog` demotes trust levels but does not halt.
  - No consecutive-loss watchdog (orthogonal to drawdown — captures regime shifts faster).
  - No threshold-trigger on `KillSwitch` (it's a passive on/off today).
  - No agent concurrency cap in `AgentRunner`.
  - No single-asset concentration check, no directional alignment check.
  - No per-broker fee or slippage models feeding into `SizingEngine` — live sizing and backtest P&L drift apart.
  - No Black–Scholes / Greeks module. `OptionsHedgingAgent` proposes trades without Greek balancing.
  - No HTF trend-filter mixin on `Agent`.
  - Triple EMA confluence and pairs-spread stat arb are not packaged as agents (the indicators exist).

**Intended outcome.** A drop-in incorporation of every go-trader pattern that adds real value, landed as a series of focused PRs that each pass `cd trading && python -m pytest tests/unit/` and leave the system more resilient. No rewrites, no cross-language runtime (we stay Python-only), no duplication of what we already do better.

---

## Roadmap Overview

| Phase | Theme | Rough size | Depends on |
|-------|-------|-----------|-----------|
| 0 | Learning memo + ADR | 1 PR (docs only) | — |
| 1 | Risk hardening — drawdown halt, consecutive-loss breaker, portfolio kill-switch, concurrency caps | 1 PR | Phase 0 |
| 2 | Concentration & directional-alignment enforcement | 1 PR | Phase 1 |
| 3 | HTF trend-filter mixin | 1 PR (small) | Phase 0 (can run in parallel with 1–2) |
| 4 | Fee & slippage models (live + backtest parity) | 1 PR (small) | Phase 0 (can run in parallel) |
| 5 | Options Greeks & pricing engine | 2 PRs (pricing, then balancer) | Phase 0 |
| 6 | Strategy library expansion (Triple EMA, pairs spread) | 1 PR | Phases 3 & 5 optional |
| 7 | Multi-exchange options comparison (shadow mode) | 1 PR (optional) | Phase 5 |
| 8 | Dashboard widgets + docs wrap-up | 1 PR | All |

Each phase is independently mergeable and adds strictly opt-in behavior (agents opt in via `agents.yaml` configuration).

---

## Phase 0 — Learning memo + ADR

**Goal.** Capture the research and incorporation decision so future contributors understand the "why."

**Files to create:**

- `docs/reference/go-trader-analysis.md` — concise audit of go-trader: what it does, what we already have (with file paths), and the prioritized gap list. Use the research summary above as the starting material.
- `docs/adr/0009-go-trader-incorporation.md` — formal ADR (follow `docs/adr/0000-template.md` numbering). Captures: context, decision (incorporate patterns 1–8 in phases), consequences, alternatives considered (e.g., rewrite scheduler in Go — rejected).

**Verification:**

- `uv run python .claude/knowledge/scripts/lint.py` passes (knowledge-base health).
- ADR numbering follows the existing pattern; `docs/adr/` remains linear.

---

## Phase 1 — Risk hardening: drawdown halt, consecutive-loss breaker, portfolio kill-switch, concurrency caps

**Goal.** Convert our existing-but-passive risk primitives into active circuit breakers. Four orthogonal failure modes get coverage:
1. **Per-agent drawdown halt** — halt a strategy once its drawdown crosses a threshold.
2. **Per-agent consecutive-loss halt** — halt after N losing trades in a row, even if drawdown is small (captures regime shifts faster than drawdown alone).
3. **Portfolio kill switch with threshold trigger** — trip the global kill switch at a hard portfolio drawdown.
4. **Agent concurrency cap** — limit the number of agents that can hold open positions simultaneously so a bad cross-strategy day can't run away.

> **See also:** `go-trader-incorporation-plan.md` sections 1 and 2 for OpenCode's concrete `PortfolioDrawdownKillSwitch` and `ConsecutiveLossCircuitBreaker` code-snippet form — use those as starting drafts when implementing this phase.

**Files to modify:**

- `trading/risk/governor.py` — extend `DrawdownWatchdog` (currently only demotes trust levels) to emit a `HALT` action when per-agent drawdown crosses a configurable threshold; add a sibling `ConsecutiveLossWatchdog` that counts consecutive losing trades from `TradeStore` and emits `HALT` on breach.
- `trading/risk/circuit_breaker.py` — reuse the existing state machine; no changes, just new call sites for the two watchdogs.
- `trading/risk/kill_switch.py` — add `arm_threshold(max_portfolio_drawdown_pct: float)` and a tick method that trips the switch automatically when `trading/risk/analytics.py::PortfolioRisk.current_drawdown` crosses it.
- `trading/agents/runner.py::AgentRunner` — add `max_concurrent_active_agents` (default None = unlimited); when the cap is reached and all slots are holding positions, defer new scan activations and log `event_type=runner.concurrency.deferred`.
- `trading/agents/router.py::OpportunityRouter` — wrap each agent's opportunity emission with a per-agent `CircuitBreaker` keyed by agent name; skip routing when the breaker is OPEN.
- `trading/config.py` — new env vars:
  - `STA_RISK_DRAWDOWN_HALT_PCT` (default 0.10)
  - `STA_RISK_CONSECUTIVE_LOSS_LIMIT` (default 5)
  - `STA_RISK_PORTFOLIO_KILL_PCT` (default 0.25)
  - `STA_AGENT_MAX_CONCURRENT_ACTIVE` (default unset)
- `trading/agents.yaml` — per-agent `risk.drawdown_halt_pct` and `risk.consecutive_loss_limit` override blocks (optional).

**Reuse:**

- `trading/risk/analytics.py::PortfolioRisk` for drawdown tracking (already computes `current_drawdown` / `max_drawdown` / `peak_equity`).
- `trading/storage/trades.py::TradeStore` as the source of per-agent trade history for the consecutive-loss watchdog.
- `trading/notifications/composite.py` to surface HALT/KILL events via existing Discord/Slack/WhatsApp stack.

**Tests:**

- `trading/tests/unit/risk/test_drawdown_halt.py` — synthetic PnL that walks the watchdog into HALT.
- `trading/tests/unit/risk/test_consecutive_loss_halt.py` — synthetic trade log triggers halt at N losses; a winning trade before N resets the counter.
- `trading/tests/unit/risk/test_portfolio_kill_switch.py` — synthetic portfolio that trips the kill switch.
- `trading/tests/unit/agents/test_router_circuit_breaker.py` — router skips routing when breaker is OPEN and resumes in HALF_OPEN.
- `trading/tests/unit/agents/test_runner_concurrency.py` — with cap=2 and two active agents holding positions, a third scan is deferred.

**Verification:**

- `cd trading && python -m pytest tests/unit/risk tests/unit/agents -v --tb=short --timeout=30`
- Manual: set `STA_RISK_DRAWDOWN_HALT_PCT=0.01` or `STA_RISK_CONSECUTIVE_LOSS_LIMIT=2`, run backtest on a losing day, confirm HALT event is logged with `event_type=risk.halt` in JSON logs.

---

## Phase 2 — Concentration & directional-alignment monitor

**Goal.** Flag when a single asset dominates the portfolio or when too many strategies align on the same side — go-trader's 60% / 75% thresholds.

> **See also:** `go-trader-incorporation-plan.md` section 3 ("Correlation Enforcement") for OpenCode's rule-based implementation draft.

**Files to create/modify:**

- `trading/risk/concentration.py` (new) — `ConcentrationMonitor` with two checks:
  - `single_asset_exposure(positions) -> dict[str, float]`: returns `{symbol: notional_pct}`; flags any > `max_single_asset_pct` (default 0.60).
  - `directional_alignment(open_opportunities) -> float`: returns share of open strategies on the same side; flags when > `max_directional_alignment_pct` (default 0.75).
  - Emits alerts through `trading/learning/correlation_monitor.py`'s alert channel (reuse the NORMAL/WARNING/CRITICAL levels and 6h cooldown).
- `trading/risk/governor.py` — wire `ConcentrationMonitor` into the capital-allocation loop so concentrated agents get size-reduced (50% on CRITICAL, 25% on WARNING, mirroring `CorrelationMonitor.should_reduce_position`).
- `trading/api/routes/risk.py` (or extend existing) — expose `/api/risk/concentration` endpoint returning current exposure and alert level.
- `trading/agents.yaml` — global `risk.concentration.*` config block.

**Reuse:**

- `trading/learning/correlation_monitor.py` — alert-level taxonomy, cooldown logic, persistence pattern.
- `trading/data/bus.py::get_sector` — for future sector-level concentration (same module can grow there).
- `trading/notifications/composite.py` — alert delivery.

**Tests:**

- `trading/tests/unit/risk/test_concentration.py` — synthetic positions that trip each threshold.
- `trading/tests/unit/api/test_risk_route.py` — route returns structured JSON.

**Verification:**

- `cd trading && python -m pytest tests/unit/risk -v --tb=short --timeout=30`
- `curl -H "X-API-Key: $STA_API_KEY" http://localhost:8080/api/risk/concentration` returns the expected shape.

---

## Phase 3 — HTF trend-filter mixin

**Goal.** Per-agent optional gate: only allow long signals when the higher-timeframe trend is up (and vice versa). Go-trader exposes this as a strategy toggle.

> **See also:** `go-trader-incorporation-plan.md` section 6 for OpenCode's draft.

**Files to create/modify:**

- `trading/agents/htf_filter.py` (new) — `HTFTrendFilter` utility class:
  - `passes(symbol, side, config) -> bool`
  - Pulls HTF bars via `DataBus.get_historical(symbol, htf_timeframe, lookback_days)`.
  - Computes trend using existing `trading/data/indicators.py::ema` (default: EMA slope over N bars).
  - Returns True when the signal side agrees with HTF trend direction.
- `trading/agents/base.py::Agent` — add `_htf_filter: HTFTrendFilter | None` wired from `AgentConfig.htf_filter` block; `scan()` opt-in wrapper method `_apply_htf_filter(opportunities)`.
- `trading/agents.yaml` — per-agent `htf_filter: {timeframe: "4h", indicator: "ema", length: 50, min_slope_bps: 5}` block.

**Reuse:**

- `trading/data/indicators.py` (EMA, slope) — do NOT add new indicator math.
- `trading/data/bus.py::get_historical` — already caches at 5m TTL.

**Tests:**

- `trading/tests/unit/agents/test_htf_filter.py` — feeds synthetic bars and verifies gating.
- `trading/tests/unit/strategies/test_rsi_with_htf.py` — integration: existing `rsi_scanner` agent with `htf_filter` block should reject opposing-trend signals.

**Verification:**

- `cd trading && python -m pytest tests/unit/agents tests/unit/strategies -v --tb=short --timeout=30`
- Run a walk-forward backtest with and without the filter on `rsi_scanner`; confirm reduced trade count and improved win rate in logs.

---

## Phase 4 — Fee & slippage models (live + backtest parity)

**Goal.** Today `trading/backtesting/engine.py` supports commission models but live sizing and expected-value calculations do not factor in per-exchange fees or expected slippage. Go-trader bakes both into every signal's EV. Close the gap so that (a) live and backtest agree, and (b) marginal-EV strategies are rejected before they trade.

> **See also:** `go-trader-incorporation-plan.md` section 5 ("Fee/Slippage Models") for OpenCode's per-broker fee-schedule draft.

**Files to create/modify:**

- `trading/costs/__init__.py` (new)
- `trading/costs/fees.py` (new) — `FeeModel` hierarchy with implementations per broker (IBKR, Alpaca, Tradier, Binance, Bitget, Kalshi, Polymarket). Returns a per-order fee given side, notional, and instrument type.
- `trading/costs/slippage.py` (new) — `SlippageModel` hierarchy:
  - `FixedBpsSlippage` (default)
  - `SpreadFractionSlippage` (uses quoted bid-ask spread, takes configurable fraction)
  - `AdvParticipationSlippage` (scales with order size vs 20-day ADV)
- `trading/costs/registry.py` (new) — `get_fee_model(broker_id)` / `get_slippage_model(broker_id)`, configured via `agents.yaml` or env.
- `trading/sizing/engine.py` — inject `FeeModel` + `SlippageModel` into `SizingEngine`; reduce sized notional by expected cost, reject trade if post-cost expected value <= 0.
- `trading/agents/router.py::OpportunityRouter` — annotate every emitted `Opportunity` with `expected_fee` and `expected_slippage` fields before risk review.
- `trading/backtesting/engine.py::BacktestEngine` — replace ad-hoc commission with the new `FeeModel` + `SlippageModel` so live and historical numbers agree.
- `trading/agents/models.py::Opportunity` — add optional `expected_fee: float` and `expected_slippage: float` fields (default 0).
- `trading/config.py` — env vars:
  - `STA_COSTS_DEFAULT_FEE_BPS` (fallback when broker has no model, default 5)
  - `STA_COSTS_DEFAULT_SLIPPAGE_BPS` (fallback, default 3)

**Reuse:**

- `trading/backtesting/engine.py::SimulatedPortfolio` — commission handling pattern is the starting point for the interface.
- `trading/data/bus.py` — ADV and quote data for slippage models.
- `trading/adapters/*/adapter.py` — per-broker fee schedules come from the adapter config.

**Tests:**

- `trading/tests/unit/costs/test_fees.py` — verify each `FeeModel` returns expected values for canonical orders (e.g., 100-share IBKR equity, 1-BTC Binance spot).
- `trading/tests/unit/costs/test_slippage.py` — each slippage model produces sane numbers at small and large size.
- `trading/tests/unit/sizing/test_sizing_with_costs.py` — marginal-EV opportunity (gross EV = 1 bp, fee = 5 bps) is rejected.
- `trading/tests/unit/backtesting/test_backtest_fee_parity.py` — live fee model and backtest fee model produce identical P&L on a canned trade sequence.

**Verification:**

- `cd trading && python -m pytest tests/unit/costs tests/unit/sizing tests/unit/backtesting -v --tb=short --timeout=30`
- Run a walk-forward backtest with and without costs enabled and log the equity-curve delta.

---

## Phase 5 — Options Greeks & pricing engine

**Goal.** Give us a real options-math layer so the existing `OptionsHedgingAgent` (and future strategies) can price options, read Greeks, and balance new trades against open Greek exposure — go-trader's key differentiator. **This phase is NOT in `go-trader-incorporation-plan.md`** — it is net new to this merged roadmap.

**Split into two PRs:**

### 5A — `trading/options/` pricing + Greeks

**Files to create:**

- `trading/options/__init__.py`
- `trading/options/pricing.py` — closed-form Black–Scholes (European) and Black-76 (futures options); binomial CRR tree for American exercise.
- `trading/options/greeks.py` — closed-form `delta`, `gamma`, `vega`, `theta`, `rho` plus a `numerical_greeks` fallback.
- `trading/options/iv.py` — Newton–Raphson implied volatility solver with a bisection fallback.
- `trading/options/contract.py` — `OptionContract` dataclass (right, strike, expiry, underlying, multiplier) separate from broker-specific models.

**Dependencies.** `scipy` is already transitively present (check `trading/pyproject.toml` first). Per CLAUDE.md "Ask first" rule, confirm before pinning versions.

**Tests:**

- `trading/tests/unit/options/test_black_scholes.py` — compare against published values (e.g., Hull textbook).
- `trading/tests/unit/options/test_greeks.py` — closed-form vs numerical differentiation agreement within 1e-6.
- `trading/tests/unit/options/test_iv_solver.py` — round-trip: price → IV → price.

### 5B — `GreekBalancer` + `OptionsHedgingAgent` refactor

> **See also:** `go-trader-incorporation-plan.md` section 4 ("Theta Harvesting Exit Rules") — OpenCode's plan partially covers this with a profit/loss/DTE exit-rule framework we'll reuse in `options_theta_harvester.py`.

**Files to create/modify:**

- `trading/options/balancer.py` (new) — `GreekBalancer.score(candidate, open_positions) -> float` returning 0.0–1.0; penalizes candidates that increase net delta / gamma / vega beyond configured bounds, rewards those that offset.
- `trading/strategies/options_hedging.py` — inject `GreekBalancer`; use score as a filter before emitting opportunities; max 4 positions per strategy (mirrors go-trader).
- `trading/strategies/options_theta_harvester.py` (new) — closes sold equity options at profit target (60%), stop loss (200%), or DTE threshold (3 days). Reuses the balancer and BS pricing for mark-to-market.
- `trading/agents.yaml` — register `options_theta_harvester` alongside existing `kalshi_theta` / `polymarket_theta`.
- `trading/adapters/ibkr/adapter.py` — ensure `get_options_chain` returns enough fields for Greeks (underlying price, IV, bid/ask). Audit first; extend only if needed.

**Reuse:**

- `trading/strategies/options_hedging.py::OptionsHedgingAgent` — keep the iron-condor / collar / protective-put selection logic.
- `trading/data/sources/broker_source.py::get_options_chain`.
- `trading/strategies/kalshi_time_decay.py` / `polymarket_time_decay.py` as reference theta-harvester patterns.

**Tests:**

- `trading/tests/unit/options/test_balancer.py` — synthetic portfolio, verify opposing-Greek candidate wins over amplifying one.
- `trading/tests/unit/strategies/test_options_theta_harvester.py` — synthetic position walks through profit/loss/DTE exits.
- `trading/tests/unit/strategies/test_options_hedging_greek_gate.py` — hedging agent rejects candidate when net vega would exceed limit.

**Verification:**

- `cd trading && python -m pytest tests/unit/options tests/unit/strategies -v --tb=short --timeout=30`
- Shadow mode: run the theta harvester on a paper broker for a week; confirm no live orders and log event stream shows entry/exit decisions.

---

## Phase 6 — Strategy library expansion

**Goal.** Package go-trader's notable unique strategies as first-class agents using our existing indicator stack. **Also not in `go-trader-incorporation-plan.md`** — net new to this merged roadmap.

**Files to create:**

- `trading/strategies/triple_ema_confluence.py` — Triple EMA (9/21/55) crossover with HTF filter (Phase 3) enabled by default. Uses `trading/data/indicators.py::ema`.
- `trading/strategies/pairs_spread.py` — statistical arbitrage on a configured pair (e.g., BTC/ETH). Z-score of log-price ratio vs rolling mean; enter on ±2σ, exit on 0. Uses `trading/data/indicators.py` where possible.
- Optional: `trading/strategies/bollinger_reversion.py`, `trading/strategies/macd_confluence.py` — only if not already covered by existing agents (audit `agents.yaml` before creating).
- `trading/agents.yaml` — register the new agents with sensible `trust_level: MONITORED`, `paper_only: true` defaults.

**Reuse:**

- `trading/data/indicators.py` for all math (EMA, MACD, Bollinger, z-score).
- `trading/agents/base.py::StructuredAgent` as the base class.
- `trading/backtesting/engine.py` for walk-forward validation.

**Tests:**

- `trading/tests/unit/strategies/test_triple_ema_confluence.py`
- `trading/tests/unit/strategies/test_pairs_spread.py`
- Walk-forward backtest on 2 years of daily bars for each; record Sharpe in test output.

**Verification:**

- `cd trading && python -m pytest tests/unit/strategies -v --tb=short --timeout=30`
- `curl -H "X-API-Key: $STA_API_KEY" http://localhost:8080/api/agents` lists the new agents as MONITORED.

---

## Phase 7 — Multi-exchange options comparison (optional)

**Goal.** Run the same options strategy against two brokers simultaneously (e.g., IBKR/CME vs Deribit crypto options) in shadow mode and log the divergence. Useful for venue-selection research, not critical.

**Files to create/modify:**

- `trading/strategies/multi_venue_shadow.py` (new) — decorator/wrapper agent that forwards the same signal to two `broker_id`s, marks one as `shadow=true`, and logs divergence.
- `trading/agents/router.py::OpportunityRouter` — already has shadow-mode; extend to accept a list of brokers per opportunity.
- `trading/api/routes/bittensor.py` or new `trading/api/routes/shadow.py` — `/api/shadow/divergence` returning per-symbol PnL divergence.

**Dependencies.** Requires a crypto options adapter (Deribit is currently absent; `trading/adapters/bitget/` has crypto options). Spike first: can we get a `get_options_chain` from bitget for the same underlying IBKR serves? If no, **defer this phase**.

**Tests:**

- `trading/tests/unit/strategies/test_multi_venue_shadow.py`

**Verification:**

- Run paper mode with two brokers; dashboard shows divergence plot.

---

## Phase 8 — Dashboard widgets + docs wrap-up

**Goal.** Make the new risk/option state visible in the existing React frontend and close out the initiative.

**Files to create/modify:**

- `frontend/src/pages/risk.tsx` (new) or extend existing risk dashboard — widgets for:
  - Per-agent drawdown + HALT state + consecutive-loss counter (from Phase 1)
  - Concurrency cap utilization (from Phase 1)
  - Concentration / directional-alignment alerts (from Phase 2)
  - Expected fees and slippage per recent opportunity (from Phase 4)
  - Net portfolio Greeks (from Phase 5)
- `frontend/src/lib/api/risk.ts` — typed client for `/api/risk/concentration`, `/api/costs/preview`, and new options-Greeks endpoint.
- `CLAUDE.md` — add new "Always do" entries for the drawdown halt env vars, the consecutive-loss limit, the concurrency cap, the costs module, and the options-math module.
- `docs/adr/0009-go-trader-incorporation.md` — update status from PROPOSED to ACCEPTED, link to the shipped PRs.
- `.claude/knowledge/articles/` — let the SessionEnd hook auto-capture; optionally add a manual compile.

**Optional polish — strategy registry decorator (from OpenCode's plan).** OpenCode proposed a `@register_strategy` decorator for auto-discovery (section 8 of `go-trader-incorporation-plan.md`). We already use `agents.yaml` as the registry and the decorator would duplicate that surface. Recommendation: **defer** unless contributors ask for it; revisit if `agents.yaml` maintenance becomes painful.

**Verification:**

- `cd frontend && npm test`
- Manual: load `http://localhost:3000/risk`; verify all widgets render with live data.

---

## Cross-cutting notes

- **Ordering / parallelism.** Phases 1, 2, 3, and 4 are independent beyond Phase 0 and can land in any order. Phase 5 depends on Phase 0 only. Phase 6 benefits from Phase 3 (HTF filter) and Phase 5 (Greeks) but is not strictly blocked by them. Phase 7 depends on Phase 5. Phase 8 depends on all earlier phases.
- **All new features are opt-in via `agents.yaml`.** Legacy agents stay off unless they add a new block — reduces blast radius.
- **No Bittensor-adjacent code is touched.** `weight_setter.py` and `taoshi-vanta/` remain untouched per CLAUDE.md "Ask first" rule.
- **No DB schema changes expected.** All new state flows through existing Postgres tables (drawdown snapshots, correlation store, performance store). If a new table is needed (e.g., `options_greeks_history`), it requires explicit approval per CLAUDE.md.
- **No changes to wallet reconstruction** (`docker-entrypoint.sh`, `B64_COLDKEY_PUB`, etc.) — off-limits per CLAUDE.md.
- **Copyright / license check.** Before porting strategy logic line-for-line from go-trader, read its LICENSE. If it is MIT or similar, attribute in file headers. If incompatible, reimplement from the conceptual description only (we have all the indicators already).

---

## End-to-end verification (post-all-phases)

1. `cd trading && python -m pytest tests/unit/ -v --tb=short --timeout=30` — all new unit tests pass.
2. `cd trading && make test` — full suite minus integration/live_paper passes.
3. `docker compose up -d postgres redis trading` — engine starts clean.
4. `curl -H "X-API-Key: $STA_API_KEY" http://localhost:8080/api/agents` — new agents listed, all MONITORED.
5. `curl -H "X-API-Key: $STA_API_KEY" http://localhost:8080/api/risk/concentration` — new endpoint returns structured JSON.
6. `curl -H "X-API-Key: $STA_API_KEY" http://localhost:8080/api/bittensor/status` — Bittensor subsystem unaffected.
7. Run a walk-forward backtest via `trading/backtesting/engine.py` with all new agents enabled; confirm equity curve, no exceptions, and live-vs-backtest P&L within the cost-model tolerance.
8. Force each of the four Phase 1 safety nets on a paper agent: (a) drawdown halt, (b) consecutive-loss halt, (c) portfolio kill-switch, (d) concurrency cap deferral. Verify each fires a Discord/Slack alert and writes the right structured-log event.
9. Navigate `http://localhost:3000/risk` — new dashboard widgets render with live data.
10. Review `docs/adr/0009-go-trader-incorporation.md` is marked ACCEPTED and links to all shipped PRs.
