# Revenue Roadmap
## agent-memory-unified → Income-Generating Platform

**Created:** 2026-04-14
**Last revised:** 2026-04-14 (post-review: re-tagged phases, removed scope fiction, added GTM, parked high-risk items)
**Status:** Supporting roadmap. **Source of truth for identity/billing/Signal-API = [`docs/superpowers/specs/2026-04-14-unified-platform-monetization.md`](../superpowers/specs/2026-04-14-unified-platform-monetization.md)**. This file sequences work, flags GTM gaps, and tracks streams that spec does not cover.
**Realistic timeline:** 6-9 months at part-time, *if* GTM lands. Without GTM, revenue stays near zero regardless of what ships.

---

## Relationship to the Unified Monetization Spec

The unified spec defines **how** we monetize (User identity, Stripe tiers, Gatekeeper redaction, Signal API surface, Explorer/Trader/Enterprise/Whale). This roadmap defines:

- The sequence of work across phases
- Streams the spec does **not** cover (Telegram alerts, whale tracker, DEX arb, Agent Memory SaaS, prediction aggregator, subnet)
- Go-to-market — the gap the spec does not address
- Parked items requiring compliance or product gates before starting

Where this roadmap mentions tiers/prices, defer to the unified spec. If the two disagree, the spec wins — open a PR to fix this file.

---

## Phase 0: Go-To-Market Foundation (NEW — blocks Phase 2)
**Effort:** 20-30h | **Revenue potential:** $0 directly, but Phase 2 revenue is conditional on this landing.

Without GTM, every Phase 2 line ships into silence. Phase 2 revenue assumptions require customers, and customers require distribution.

| # | Item | Effort | Done when |
|---|------|--------|-----------|
| 0.1 | Landing page + waitlist | 4-6h | Page live, email capture working, ≥1 CTA per tier |
| 0.2 | Pricing validation interviews | 8-10h | 5 customer discovery calls logged; price points sanity-checked vs willingness-to-pay |
| 0.3 | Competitor scan | 4-6h | Written comparison vs CoinSignals, TradingView alerts, Arkham, Nansen, Dune, whalemap; feature/price table |
| 0.4 | First-10-customers plan | 4-6h | Named list: where each of the first 10 comes from (Bittensor Discord, r/algotrading, X, existing network, etc.) with outreach channel |
| 0.5 | Legal/compliance memo | 4-6h (+ external review) | Written answer on: "is selling signals financial advice under our setup?" and "what disclaimers are required?" |

**Gate:** Do not begin Phase 2 paid items until 0.2 + 0.5 are complete.

---

## Phase 1: Foundation (Week 1-2)
**Effort:** 20-30h | **Revenue potential:** $0 — this phase is ops/infra hygiene, **not revenue**. Tagged as such to fix the original roadmap's accounting error.

### 1.1 Telegram Bot for Arb Alerts
| Item | Detail |
|------|--------|
| Effort | 2-3h |
| Category | **Internal tooling / user engagement** (not revenue) |
| Description | Real-time notifications on spread opportunities |
| Implementation | `python-telegram-bot` → subscribe to `arb.spread` events → alert on gap > threshold. Follows existing `trading/notifications/{slack,discord,whatsapp}.py` pattern. |
| Files | `trading/notifications/telegram.py`, env vars for bot token |
| Done when | Bot sends spread alerts within 5s of detection |

### 1.2 Grafana/Prometheus Metrics
| Item | Detail |
|------|--------|
| Effort | 6-10h (previously estimated 4-6h; bump for dashboard authoring + alert rules) |
| Category | **Observability** (not revenue) |
| Description | Visualize validator scoring, arb execution, system health |
| Implementation | `prometheus-fastapi-instrumentator` → Grafana dashboards |
| Files | `trading/metrics/`, dashboard JSON exports |
| Done when | Live dashboards showing: validator rank, arb P&L, spread detection rate; 3+ alert rules firing |

### 1.3 Backtesting Arb Strategy
| Item | Detail |
|------|--------|
| Effort | 8-14h (previously 6-8h; bump for cost/fee modeling + report tooling) |
| Category | **Strategy validation** (gates Phase 1.4 and the "improve existing P&L" track) |
| Description | Validate `min_profit_bps`, `max_position_usd` with historical spread data; include fees, gas, slippage |
| Implementation | Replay SpreadStore history, simulate execution, calculate realized P&L net of costs |
| Files | `scripts/backtest_arb.py`, results in `docs/backtests/` |
| Done when | Report shows cost-adjusted Sharpe > 1.0 and max drawdown assumption. If Sharpe < 1, **kill 1.4 and the arb track entirely.** |

### 1.4 Add Exchange (one, pick after 1.3)
| Item | Detail |
|------|--------|
| Effort | 16-24h per exchange (previously 8-12h; bump for perp mechanics: funding, liquidation, margin) |
| Category | **Conditional on 1.3** — only if backtest shows edge |
| Description | Integrate one perp DEX (Hyperliquid *or* dYdX — not both up-front) |
| Implementation | New adapter in `trading/adapters/<name>/` following bitget pattern; funding-rate tracking mandatory |
| Done when | Live price feeds, paper-traded for 1 week, post-cost spreads match backtest |

---

## Phase 2: Monetization Core (Week 3-10)
**Effort:** 120-180h (revised up from 54-70h) | **Revenue potential:** $0-2,000/mo realistic, $2-10k/mo optimistic, gated on Phase 0.

### 2.1 Signal API — **delegated to unified spec**
See `docs/superpowers/specs/2026-04-14-unified-platform-monetization.md` and `docs/superpowers/specs/2026-04-14-signal-api-design.md`. Effort ≈ **80-120h** (spec itself quotes 10-13 days; add 3-5× buffer for billing, docs, support, ops, edge cases). Original roadmap's "8-10h" was ~10× low.

Pricing, tiers, and Stripe integration: per unified spec. **Do not ship with crypto payments as v1** — Stripe-only until volume justifies dual rails.

### 2.2 Whale Wallet Tracker
| Item | Detail |
|------|--------|
| Effort | 16-24h (previously 8-12h; bump for reorg handling, dedup, alert fatigue tuning) |
| Revenue | $200-800/mo realistic if bundled as Pro perk; standalone product unlikely to outcompete Arkham/Nansen |
| Implementation | Etherscan/BSCScan API → threshold detection → Telegram/webhook alerts |
| Files | `trading/strategies/whale_tracker.py`, `trading/notifications/whale_alerts.py` |
| Done when | Tracks wallets >$1M, alerts on moves >$100k, dedup window prevents alert storms |
| Positioning | Ship as **Trader/Enterprise-tier feature of the unified platform**, not a separate product |

### 2.3 Cross-DEX Arbitrage — **strategy risk, not scope risk**
| Item | Detail |
|------|--------|
| Effort | 40-80h if pursued seriously (previously 12-16h) |
| **Viability** | **Low.** MEV searchers with private orderflow dominate on-chain arb. Retail success requires block-builder access, flashloan infra, or a structural edge we do not have. |
| Recommendation | **Do not start without a research spike** proving edge on mainnet-forked simulation first. Budget 8-16h for the spike, kill the feature if the spike is negative. |
| Files | `trading/strategies/dex_arb_research.py` (spike only) |

### 2.4 ~~Copy Trading Layer~~ — **PARKED**
**Parked pending compliance memo (Phase 0.5).** Rationale:

- Order routing against customer brokerage credentials + profit share = likely advisory/asset-management under SEC (equities) or CFTC/NFA (derivatives). "Not financial advice" disclaimers are not a defense here.
- Technical scope was also undersold at 16-20h: credential custody, heterogeneous broker replication, fill-drift reconciliation, profit-split accounting, dispute handling — realistic scope is 200-400h.
- Revenue claim of $1000-5000/mo requires winning trades on real customer capital — incident risk is asymmetric.

**Unpark condition:** Compliance memo returns a workable structure (e.g., signals-only with customer-executed trades, or regulated entity partnership).

### 2.5 ~~Cross-Platform Arbitrage (Kalshi ↔ Polymarket)~~ — **PARKED** (2026-04-14)

Parked during Track T dogfood investigation. Live-system inspection revealed the strategy is **blocked at the data-fetch layer**, not the matcher. Specifics:

- **Kalshi `get_markets(category=...)` filter is ignored.** With `kalshi_categories=["economics","politics","climate"]` configured, live scan returns 1500 markets that are all sports-prop aggregates (ticker pattern `KXMVESPORTS*`/`KXMVECROSSCATEGORY*`) with `category=''` (empty string).
- **Polymarket `get_markets(tag=...)` filter is ignored and data is stale.** With `polymarket_tags=["politics","crypto","climate"]`, live scan returns 3000 markets that are all 2023-dated NCAAB/NBA games (titles like `'NCAAB: Arizona State Sun Devils vs. Nevada Wolf Pack 2023-03-15'`) with `category='All'`.
- With both sides returning `"other"` after `normalize_category()`, the +0.10 category bonus never fires, and Jaccard on disjoint-domain text is ~0 across all 4.5M potential pairs — `candidates=0` at `min_similarity=0.20`.
- Threshold tuning and matcher changes cannot fix this; both data adapters need work first.

**Scope to unpark:**
- Fix `trading/adapters/kalshi/` `get_markets` category filter — currently returning full universe regardless of filter.
- Fix `trading/adapters/polymarket/` `get_markets` tag filter AND source of stale 2023 data (likely a cache / wrong endpoint / test-fixture leak).
- Verify against live API responses that the filter actually narrows.
- Budget: 2-5 days of adapter work, uncertain payoff.

**Unpark condition:** Both adapter bugs fixed AND a one-scan test where `kalshi_categories=["politics"]` returns <50 Kalshi markets all tagged with politics-domain tickers/titles, and same for Polymarket side. Only then is it worth re-running `match_markets()` to see if candidates appear.

**Preserved:** `agents.yaml` `min_match_similarity: 0.20` (seed value, more permissive than the original 0.35; inert against current DB state but correct for any future fresh install). A lightweight count-log remains in `cross_platform_arb.py` (`kalshi=N poly=N candidates=N`) for future diagnosis. Title-dump debug log removed. DB `agent_registry.parameters` row for `cross_platform_arb` left at `0.20` (doesn't matter while parked).

---

## Phase 3: Platform Play (Month 3+)
**Effort:** 200-400h+ | **Revenue potential:** Speculative until Phase 2 validates demand.

### 3.1 Agent Memory as Service
| Item | Detail |
|------|--------|
| Effort | 100-200h (previously 20-30h) |
| Revenue | $500-3000/mo realistic in first year of B2B SaaS |
| Scope | Multi-tenant isolation, usage-metered billing, tenant auth, SOC2-lite posture, ops on-call |
| Gate | Only start after ≥1 paying design partner committed in writing |

### 3.2 Prediction Market Aggregator
| Item | Detail |
|------|--------|
| Effort | 60-100h (previously 24-32h) |
| Revenue | $200-1500/mo (affiliate + thin premium) — small TAM vs effort |
| Risk | Kalshi + Polymarket APIs have rate limits, regulatory gaps (Polymarket blocks US IPs), and arbitrage windows measured in seconds |
| Priority | **Low.** Only pursue if Phase 2 Signal API reveals prediction-market demand from customers. |

### 3.3 ~~Bittensor Subnet 2.0~~ — **PARKED**
**Parked.** Rationale:

- Subnet registration alone requires significant TAO stake (recurring). Not a 40-60h project — mechanism design, validator/miner protocol, and incentive tuning are multi-month engagements.
- We already validate on Subnet 8 (Taoshi). Launching a competing subnet dilutes focus and capital.
- Revenue is TAO-price dependent, which is not a business model we control.

**Unpark condition:** Standalone go/no-go doc with: (a) mechanism design draft, (b) TAO budget, (c) evidence from Bittensor community of demand for the specific niche, (d) explicit rationale for why this is better than scaling our Subnet 8 position.

---

## New track: Improve Existing Trading P&L
**Effort:** 40-80h | **Revenue potential:** highest $/h on the roadmap.

The existing trading engine (13 agents, validator, ArbExecutor) is the cheapest revenue unlock we have — no new customers required. Every 10 bps of improved return on deployed capital beats a dozen low-ticket subscriptions on a risk-adjusted basis.

| # | Item | Effort | Done when |
|---|------|--------|-----------|
| T.1 | Validator score optimization | 12-20h | Measurable rank improvement on Subnet 8 over 30 days |
| T.2 | Arb cost model (fees, gas, slippage, funding) | 10-16h | Realized P&L within 20% of pre-trade estimate |
| T.3 | Strategy ensemble weighting review | 8-12h | Sharpe improvement documented in backtest |
| T.4 | Kill-switch + position-sizing tightening | 8-12h | Max drawdown bounded; test coverage for edge cases |
| T.5 | Paper → small live capital promotion criteria | 4-8h | Written criteria; first promotion executed |

This track has **no GTM dependency** and compounds with Phase 2 (better live track record → easier signal-API sales).

---

## Revised Execution Timeline

```
Week 1-2:   Phase 0 GTM (20-30h) + Phase 1 Foundation (20-30h)       ← parallel
Week 3-4:   Trading P&L track T.1-T.3 (30-48h)                        ← revenue-compounding
Week 5-10:  Signal API per unified spec (80-120h)                     ← first subscription revenue
Week 11-14: Whale Tracker as Trader-tier perk (16-24h)
            + DEX arb research spike (8-16h, kill-early)
Month 4+:   Agent Memory SaaS *only if* design partner signed
Parked:     Copy Trading (until compliance memo), Subnet 2.0, Prediction Aggregator
```

## Revised Revenue Trajectory

Prior version claimed $10k-50k/mo by Month 5 with no GTM plan. Realistic trajectory *conditional on Phase 0 landing*:

| Month | Cumulative effort | Realistic revenue | Optimistic revenue | Assumption |
|-------|-------------------|-------------------|--------------------|------------|
| 1 | 40-60h | $0 | $0 | Phase 0 + Phase 1 don't generate revenue |
| 2 | 70-108h | $0-200 | $0-500 | Waitlist + first design conversations |
| 3 | 150-228h | $200-1,000 | $500-2,500 | Signal API soft launch, 5-20 paid users |
| 4 | 190-292h | $500-2,000 | $1,500-5,000 | 20-50 paid users, whale tracker bundled |
| 5-6 | 230-372h | $1,000-3,500 | $3,000-8,000 | 50-120 paid users, Enterprise tier lands first customer |

**If Phase 0 fails** (no distribution, pricing wrong, compliance blocker): all Phase 2 revenue goes to ~$0. This is the dominant risk, not technical risk.

---

## Revised Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **No distribution → no customers** | **High** | **High** | Phase 0 gates all paid work |
| **Signals classified as financial advice** | **Medium** | **High** | Phase 0.5 compliance memo before launch; signals-only, no execution-on-behalf |
| Copy-trading regulatory exposure | High (if we pursue) | Very High | **Parked** until compliance path cleared |
| Arb execution losses | Medium | Medium | Phase 1.3 backtest gate; small position sizing; T.2 cost model |
| Subnet 2.0 TAO burn without ROI | High (if we pursue) | Medium | **Parked** until standalone go/no-go doc |
| DEX arb MEV'd by searchers | High | Low (bounded by research spike) | 8-16h spike; kill if negative |
| Effort estimates remain optimistic | Medium | Medium | 3-5× buffers applied; re-baseline after Phase 1 actuals |
| Competitor (TradingView/Arkham/Nansen) ships equivalent | Low | Medium | First-mover on Bittensor-consensus signals is real; own the niche |

---

## Next Steps

1. **This week:** Start Phase 0.1 (landing page) + Phase 1.1 (Telegram bot) in parallel. Low effort, unblocks everything.
2. **This week:** Begin compliance memo (Phase 0.5) — external if needed. This is the longest-lead item.
3. **Week 2:** Finish Phase 1 backtest (1.3). Kill-or-proceed decision on arb track.
4. **Week 3:** If compliance memo green, begin Signal API per unified spec. If not, pivot roadmap to Trading P&L track only.
5. **Re-baseline this document** after Phase 1 actuals are known.

## What is NOT on this roadmap (and why)

- Copy Trading — parked, compliance
- Bittensor Subnet 2.0 — parked, needs standalone analysis
- Crypto payments for Signal API — deferred until volume justifies second billing rail
- Prediction Market Aggregator — low priority until Signal API reveals demand
- Two new exchanges at once — 1.4 picks one, based on 1.3 backtest

If you think something should be un-parked, write the unpark-condition doc first.

---

## Subtask Inventory Review (Signal API + Agent Auth API)

As of 2026-04-14, two subtask trees exist under `.tmp/tasks/`:

- `.tmp/tasks/signal-api/` — 11 subtasks + `task.json`
- `.tmp/tasks/agent-auth-api/` — 11 subtasks + `task.json`

Each subtask has acceptance criteria, deliverables, dependencies, and parallel flags baked in. This is the right shape for agent-driven execution.

### What's strong

- Foundation-first ordering (01 = DB schema in both trees)
- Test subtask (11) correctly gates on all prior work via `depends_on: [01..09]`
- Billing critical path is explicit: `01 → 02 → 03`
- File paths match existing conventions (`trading/api/routes/...`, `trading/models/...`, `trading/tests/unit/...`)
- Acceptance criteria are observable (HTTP status codes, SQL columns, header names) rather than fuzzy

### What needs fixing before execution

These issues would cause the two trees to build a structure that conflicts with the unified monetization spec. **Fix the inventory before running `coder-agent` on it.**

| # | Issue | Impact | Remediation |
|---|-------|--------|-------------|
| S1 | Both trees reference **superseded** specs (`2026-04-14-signal-api-design.md`, `2026-04-14-agent-auth-api-design.md`). The unified spec (`2026-04-14-unified-platform-monetization.md`) replaces them and introduces a shared `users` table. | High — wrong DB schema; tier names mismatch (Free/Pro/Enterprise vs Explorer/Trader/Enterprise/Whale); two parallel identity models | Re-point `context_files` in both `task.json` files to the unified spec. Rebaseline subtask 01 in both trees. |
| S2 | **No `users` table subtask exists.** Unified spec requires a `users` table bridging human owners to agents, and an `identity.agents.user_id` FK. Subtasks 01 in both trees jump straight to feature tables. | High — blocks both APIs; identity model fragments into 3 disjoint tables (`signals_api_keys`, `auth_accounts`, `identity.agents`) | Add new **prereq subtask 00** (or rework 01): creates `users` + `platform_tier` enum + `identity.agents.user_id` per unified spec §6. Signal API + Auth API both `depends_on: [00]`. |
| S3 | **Two separate Stripe surfaces.** `signal-api-02/03` and `agent-auth-api-03` each create their own checkout + webhook handlers, products, and price IDs. | Medium — two billing silos; a user who wants both products pays two subscriptions; duplicate code; doubled webhook attack surface | Consolidate: one `trading/api/routes/billing/checkout.py` and one `trading/api/routes/billing/stripe_webhooks.py` shared across products. Price IDs stay per-product but the surface is unified. |
| S4 | **Two separate rate-limit middlewares** (`signals_limiter.py`, `auth_limiter.py`). Both do the same thing — look up identity, check Redis tier bucket, return 429. | Medium — duplicate code; divergent behavior risk | Extend the existing `trading/api/middleware/limiter.py` with a `tier_resolver` callable (same pattern as the 2026-04-13 `get_tier_limit` fix per memory `project_defensive_perimeter_gaps`). One middleware, two resolvers. |
| S5 | **Two separate landing pages** (`/signal-api`, `/agent-auth`). Unified spec implies one platform subscription. | Medium — fragments brand + conversion | Single `/pricing` page with tabs per product, or a unified card grid. Keep product-specific dashboards (`/signal-api/dashboard`, `/agent-auth/dashboard`). |
| S6 | **No GTM subtasks** — no landing page copy, pricing validation, competitor comparison, first-10-customers plan, compliance memo. | High — Phase 0 of this roadmap is absent from the execution inventory | Add a third subtask tree `.tmp/tasks/phase-0-gtm/` covering items 0.1-0.5 above. Gate paid Phase 2 subtasks on Phase 0 completion. |
| S7 | **Parallelism claim is optimistic.** "Both can be built in parallel" — they can't until S1/S2/S3 are resolved (shared schema, shared Stripe handler). | Medium — risk of merge conflicts and schema thrash if run simultaneously | After S2 prereq lands, Signal-API 04-09 and Auth-API 04-09 *can* run in parallel. 01-03 in each tree must be sequenced with the shared prereq. |
| S8 | **Token format drift.** `agent-auth-api-05` specifies `amu_{agent_name}.{base64_url_safe_signature}`. Spec specifies `amu_{agent_name}.{jwt_payload.signature}`. Existing `trading/api/identity/tokens.py` uses SHA-256 hashing (not JWT). | Low — cosmetic but will trip test assertions | Pick one. Prefer the existing `identity/tokens.py` pattern since it's already in production and covered by tests. |
| S9 | **No compliance gate in inventory.** Subtask 11 (tests) passes regardless of whether the legal memo (Phase 0.5) has returned. | High — ships product that may be classified as financial advice | Add a final `signal-api-12: compliance-gate` subtask with acceptance criterion "written compliance memo in `docs/compliance/signals-memo.md` cleared by external review." Block merge-to-main without it. |
| S10 | **No observability subtasks.** Billing + token-verification are the two highest-blast-radius paths. Neither tree has logging/metrics/alerting. | Medium — you will not know when Stripe webhooks silently fail or when token verification latency spikes | Add observability to subtask 07 (usage) and extend rate-limit middleware (S4) with structured log events. Mirror the `structured logging` convention from `docs/adr/0008`. |
| S11 | **No idempotency-key column for Stripe webhook dedup** in subtask 01 schemas, despite subtask 03 acceptance criterion "Idempotent handling (check event ID not already processed)." | Low — the acceptance criterion isn't satisfiable against the schema as written | Add `stripe_events (event_id TEXT PRIMARY KEY, received_at TIMESTAMPTZ, processed BOOL)` to S2 remediation. |
| S12 | **Subtask effort sum is not stated.** Per review, Signal API alone is 80-120h; Agent Auth API is similar. The 22-subtask plan should carry effort hints so executors can schedule realistically. | Low — planning hygiene | Add `estimated_effort_hours` field to each subtask JSON. Start at 4-8h for schema/CRUD, 8-16h for middleware/webhooks, 16-24h for landing+dashboard. |

### Critical-path reconciliation

Both trees currently claim:

- Signal API: `01 → 02 → 03 → 11` **or** `01 → 04 → 05/06/07/08 → 11`
- Agent Auth API: `01 → 02 → 03 → 11` **or** `01 → 04 → 05 → 06 → 11`

After applying S2 (users-table prereq), the real unified critical path is:

```
00 (users table + platform_tier)           ← shared prereq
  ├── signal-api-01 (signals_api_keys)
  │     ├── signal-api-04 (key CRUD)  ──┐
  │     │     ├── 05 (signals)          │
  │     │     ├── 06 (opportunities)    ├── 11 (tests)
  │     │     ├── 07 (usage)            │
  │     │     ├── 08 (rate limit)       │
  │     │     └── 09 (webhooks) ────────┘
  │     └── billing-shared-02/03 (shared checkout + stripe hook)
  └── agent-auth-api-01 (auth_accounts + auth_tokens)
        ├── 02 (accounts) → 04 (agents) → 05 (tokens) → 06 (verify)
        │     └── 07 (audit), 08 (rate limit), 09 (scopes) ──┐
        │                                                     └── 11 (tests)
        └── billing-shared (same as above; NOT duplicated)
```

Then: `signal-api-12` (compliance gate) + `phase-0-gtm` (waitlist, pricing validation, compliance memo, competitor scan) gate the actual revenue launch.

### Reconciled Subtask Breakdown (authoritative)

**Top priority (2026-04-14 pivot): Track T — Personal Capital Proving Ground.** Eat our own dogfood on the user's personal brokerage + live TAO validator *before* productizing. Track T gates the others — A-F slide right. Rationale in Dogfood Pivot note below. Everything else runs after Track T demonstrates edge (or is killed by it).

The existing `.tmp/tasks/signal-api/` and `.tmp/tasks/agent-auth-api/` trees are kept for reference but need rebaselining. The breakdown below **supersedes those trees** — when regenerating JSON subtasks for `coder-agent`, use this as the source. Every subtask has: dependencies, parallel flag, effort hint, and acceptance criteria drawn from the unified spec.

#### Track T: Personal Capital Proving Ground (top priority — gates paid launch)

Capital context: live Taoshi validator on Subnet 8 (UID 144) + $11k USD in user's personal brokerage, of which $2-3k is the planned experimental sleeve. No external funding. Objective: build a 60-90 day audited live P&L curve that validates whether the 13-agent ensemble + arb executor have real edge net of costs. If yes, that curve becomes Track E's strongest marketing asset. If no, we find out on $500 instead of failing in public — and the roadmap pivots.

| Seq | Title | Depends on | Parallel | Effort |
|-----|-------|------------|----------|--------|
| T.1 | Validator score optimization — measure baseline rank/emissions on Subnet 8, tune scoring thresholds in `evaluator.py`, DO NOT touch `weight_setter.py` submission logic | — | Yes | 12-20h |
| T.2 | Arb cost model — `CostModel` class accounting for per-venue fees + gas + slippage; backtest runner replays `SpreadStore` history; Sharpe report drives kill-or-go on arb track | — | Yes | 10-16h |
| T.3 | Strategy ensemble review — backtest all 13 agents through T.2 cost model, rank by risk-adjusted return, drop/reweight losers, updated `agents.yaml` with performance-justified allocations | T.2 | No | 8-12h |
| T.4 | Kill-switch + position-sizing tightening — per-agent `max_position_usd` caps, per-hour loss circuit breakers, integration test that kill-switch actually halts orders | T.3 | No | 8-12h |
| T.5 | Paper → live promotion criteria — written gates in `docs/trading/live-promotion-criteria.md` (e.g., 30 trading days paper, Sharpe > 1.0, max DD < 10%, 100+ trades); first-promotion runbook naming exact agent + broker + size | T.3, T.4 | No | 4-8h |

**T.2 acceptance details** (this is the unblocker — runnable this week):
- `trading/execution/cost_model.py` — `CostModel.expected_profit_bps(venue_a, venue_b, notional_usd, orderbook_snapshot) -> Decimal`
- Fees sourced from existing broker adapter configs; slippage modeled from top-of-book depth in recent `SpreadStore` samples
- `scripts/backtest_arb.py` replays at least 30 days of `SpreadStore` history; simulates order fills using cost model; outputs trades CSV + summary (Sharpe, Sortino, max DD, win rate, avg net bps)
- Report written to `docs/backtests/arb-YYYY-MM-DD.md`
- **Kill-or-go criterion**: if cost-adjusted Sharpe < 1.0 on 30-day backtest, arb track is killed for personal capital — no live sleeve, roadmap's Track 1.4 exchange-add also killed.

**T.5 acceptance details** (the gate that actually lets real dollars move):
- Promotion criteria doc includes both *quantitative* gates (Sharpe, DD, trade count, paper duration) and *operational* gates (structured logs clean, kill-switch verified, alerts firing)
- First-promotion runbook is specific: "deploy agent `<name>` via `<broker>` adapter, initial position $500, `max_position_usd=$100`, hard stop on -$50 daily loss"
- Runbook includes rollback: how to unwind if performance diverges from paper by >2σ in first 2 weeks

**Track T total: 42-68h** over ~2 weeks of focused work. Then 4-8 weeks of paper trading (clock time, not effort) before T.5 triggers live promotion. Real revenue track for personal accounts doesn't begin until week 6-10; Signal API conversations (Track E.02) get the resulting P&L curve as marketing around week 12-16.

**What happens after Track T:**
- **If edge is real** (Sharpe ≥ 1.0 on cost-adjusted backtest AND paper trading): proceed to Tracks A-E with a strong fact pattern for Track E.02 pricing conversations and Track E.05 compliance memo.
- **If edge is marginal** (Sharpe 0.5-1.0): narrow the deployed strategy set to the top 1-2 performers; Tracks C/D still viable but compete harder on marketing, not on claimed performance.
- **If edge is absent** (Sharpe < 0.5): kill the arb track and monetization-via-signals direction. Pivot the roadmap to Agent Auth API (Track D) as the primary revenue surface — identity-as-a-service doesn't depend on having tradeable edge.

---



#### Track A: Platform Foundation (shared prereq — blocks all paid work)

| Seq | Title | Depends on | Parallel | Effort |
|-----|-------|------------|----------|--------|
| A.01 | `users` table + `platform_tier` enum + `identity.agents.user_id` FK + agent webhook/custom_scopes extensions | — | No | 4-8h |
| A.02 | `stripe_events` idempotency table + `is_duplicate(event_id)` helper | A.01 | No | 2-4h |

**A.01 acceptance criteria:**
- `platform_tier` enum: `explorer`, `trader`, `enterprise`, `whale` (unified spec §6)
- `users`: `id UUID PK`, `email UNIQUE`, `hashed_password`, `tier platform_tier DEFAULT 'explorer'`, `stripe_customer_id UNIQUE`, `stripe_subscription_id`, `agents_count INT DEFAULT 0`, `created_at`, `updated_at`
- `identity.agents`: ADD `user_id UUID REFERENCES users(id)`, `webhook_url`, `webhook_secret_hash`, `custom_scopes TEXT[] DEFAULT '{}'`
- All three schema sources updated: `scripts/init-trading-tables.sql`, `trading/storage/memory.py` `_INIT_DDL`, `trading/storage/memory.py` `_migrations` (per `reference_schema_three_sources` memory)
- Parity test: `trading/tests/unit/test_users_schema_parity.py`
- SQLAlchemy model: `trading/models/user.py`

**A.02 acceptance criteria:**
- `stripe_events`: `event_id TEXT PK`, `event_type`, `received_at`, `processed BOOL DEFAULT FALSE`, `processed_at`, `payload_hash`
- Index on `(processed, received_at)` for dead-letter sweeps
- Helper: `trading/api/routes/billing/idempotency.py:is_duplicate(event_id) -> bool`

---

#### Track B: Shared Billing Surface (one Stripe surface, many products)

| Seq | Title | Depends on | Parallel | Effort |
|-----|-------|------------|----------|--------|
| B.01 | `BillingProductRegistry` + shared checkout endpoint (`POST /api/v1/billing/checkout`) | A.01 | No | 8-12h |
| B.02 | Shared Stripe webhook dispatcher with idempotency (`POST /api/v1/billing/stripe/webhook`) | B.01, A.02 | No | 12-16h |
| B.03 | Unit tests: registry round-trip, idempotency, signature verification, dispatch, core vs product handler order | B.01, B.02 | No | 6-10h |

**B.01 behavior:**
- Registry: `register(product_id, price_ids, success_path, cancel_path, on_subscription_created, on_subscription_updated, on_subscription_deleted)`
- Checkout: accepts `{product_id, tier, user_id}`, looks up `price_id`, creates Stripe Checkout, returns `{checkout_url, session_id}`
- Persists `users.stripe_customer_id` on first checkout; errors 404/422/502 as appropriate
- Structured log event: `billing.checkout_created`

**B.02 behavior:**
- Verifies `Stripe-Signature` header; 400 on invalid
- Checks `stripe_events` for event id; 200 immediately on duplicate; insert row before dispatch
- Core events update `users.tier` / `stripe_subscription_id` product-agnostically; product handlers run AFTER core
- Handler exception leaves `processed=FALSE` so Stripe retries
- Structured log event: `billing.webhook_dispatched`

---

#### Track C: Signal API (revised inventory)

All subtasks depend on Track A. Subtasks that previously created their own Stripe surface now integrate with Track B.

| Seq | Title | Depends on | Parallel | Effort |
|-----|-------|------------|----------|--------|
| C.01 | `signals_api_keys` + `signals_api_usage` tables (FK → `users.id`) | A.01 | No | 4-8h |
| C.02 | Register Signal API with `BillingProductRegistry` (Trader $49 / Enterprise $199 price IDs, success/cancel paths, key-creation handler) | B.01, C.01 | Yes (with D.02) | 2-4h |
| C.03 | Signal API webhook handler (plugs into B.02: creates `signals_api_keys` row on checkout.completed; emails key) | B.02, C.02 | No | 4-6h |
| C.04 | API key CRUD (`POST/GET/DELETE /api/v1/signals/keys`) — SHA-256 hash storage, `amu_sig_sk_live_*` format | C.01 | Yes | 6-10h |
| C.05 | Signals endpoint with tier filtering (Explorer = 1hr delay, BTC/USD only, strip confidence/reasoning; Trader = real-time all symbols; Enterprise = +reasoning) | C.01, C.04 | Yes | 8-12h |
| C.06 | Opportunities endpoint (same tier rules as C.05) | C.01, C.04 | Yes | 4-8h |
| C.07 | Usage tracking endpoint + Redis counters + Postgres flush on period end | C.01, C.04 | Yes | 6-10h |
| C.08 | Tier-aware rate-limit middleware — **extends existing `trading/api/middleware/limiter.py`** with a tier resolver (not a parallel middleware). Per-tier burst limits per unified spec §5. | C.01, C.04 | Yes | 6-10h |
| C.09 | Webhook registration + HMAC delivery (Enterprise only; 3 retries with exponential backoff) | C.01, C.04 | No | 8-12h |
| C.10 | Unified `/pricing` page with Signal API tab + product dashboard (`/signal-api/dashboard`) for keys/usage/webhooks | B.01, C.04 | No | 16-24h |
| C.11 | Unit tests covering C.01-C.09 | C.01-C.09 | No | 8-12h |
| C.12 | **Compliance gate** — external legal memo in `docs/compliance/signals-memo.md`; blocks merge-to-main | C.11, Phase-0.05 | No | 4-8h ours + external review |

**Track C total: 76-124h** (vs roadmap's original "8-10h" — revision per review).

---

#### Track D: Agent Auth API (revised inventory)

Tier names aligned with unified spec: **Explorer** (was Hobby) / **Trader** (was Pro) / **Enterprise** (was Scale) / **Whale** (custom scopes). Original Hobby/Pro/Scale nomenclature retired.

| Seq | Title | Depends on | Parallel | Effort |
|-----|-------|------------|----------|--------|
| D.01 | `auth_tokens` table only (agents/accounts live in `users` + `identity.agents` from Track A) | A.01 | No | 2-4h |
| D.02 | Register Agent Auth API with `BillingProductRegistry` (Trader $49 / Enterprise $199 price IDs — aligned with unified tiers, not separate $29/$99) | B.01, D.01 | Yes (with C.02) | 2-4h |
| D.03 | Agent Auth webhook handler (plugs into B.02: creates account metadata on checkout.completed) | B.02, D.02 | No | 4-6h |
| D.04 | Agent CRUD + quota enforcement (`POST/GET/PATCH/DELETE /api/v1/auth/agents`). Quota: Explorer=5, Trader=50, Enterprise=Unlimited. `users.agents_count` atomic increment/decrement. | D.01 | Yes | 8-12h |
| D.05 | Token generation — **reuses** `trading/api/identity/tokens.py` SHA-256 + HMAC pattern (retires the JWT drift from original subtask). `amu_{agent_name}.{signature}` format; shown once at creation. | D.01, D.04 | No | 6-10h |
| D.06 | Token verification endpoint (`GET /api/v1/auth/verify`) — finds by hash, checks `revoked_at IS NULL`, updates `last_used_at`, emits `token.verified` audit event | D.01, D.05 | No | 4-8h |
| D.07 | Audit log query endpoint (Explorer = 403; Trader = 30-day retention; Enterprise/Whale = unlimited) | D.01, D.06 | Yes | 6-10h |
| D.08 | Tier-aware rate-limit middleware — **extends existing limiter** (same pattern as C.08, shared tier resolver) | D.01, A.01 | Yes | 4-6h (reuses C.08 infra) |
| D.09 | Scope enforcement + custom scope registration — extends existing `require_scope()` to check `identity.agents.scopes + custom_scopes`. Whale-tier only for custom scope API. | D.01, D.05, D.06 | No | 6-10h |
| D.10 | Agent Auth tab on unified `/pricing` page + product dashboard (`/agent-auth/dashboard`) for agents/tokens/audit/scopes | B.01, D.04 | No | 16-24h |
| D.11 | Unit tests covering D.01-D.09 | D.01-D.09 | No | 8-12h |

**Track D total: 66-106h**.

---

#### Track F: Crypto Tipping / Reputation Boosts (folded from `2026-04-14-crypto-tipping-design.md`)

Zero-custody tipping of autonomous agents via USDC on Base. Off-chain Tip→Agent mapping (no per-agent wallets). Boosts `agent_elo_ratings` proportional to verified tip. Priority: **low** — reputation perk, not a revenue driver. Run only after Track C ships and when a compliance memo (Track E.05 or a dedicated OFAC memo) clears it.

**Kept from original spec:**
- Base L2 + USDC choice (low gas, fiat-backed stablecoin, Coinbase regulatory posture)
- Single-platform-treasury model (`PLATFORM_TREASURY_ADDRESS`, multi-sig) — no per-agent wallets
- Off-chain `Tip → Agent` mapping in `crypto_tips` PG table
- Four-plus-one verification checks: status=1, destination=treasury, token=Base-USDC-contract, amount matches claim, idempotency via `tx_hash UNIQUE`
- Read-only backend (backend never signs, never holds keys)
- `crypto_tips` schema (with the fixes below)

**Fixed before keeping (spec claimed "no TBDs" but had real gaps):**

| # | Gap in original spec | Fix |
|---|-----------------------|-----|
| F.g1 | No reorg handling — Base L2 reorgs can retroactively invalidate a verified tx | Wait N block confirmations (default 12 ≈ 24s on Base) before crediting; sweep job reverts credits on reorg-invalidated tx |
| F.g2 | Race: same `tx_hash` submitted concurrently → RPC verified twice → double credit risk if UNIQUE index race loses | Wrap credit in transaction with `INSERT ... ON CONFLICT (tx_hash) DO NOTHING RETURNING` — only the winning row applies the Elo boost |
| F.g3 | Single RPC provider = single point of failure | Primary + secondary RPC chain (Alchemy → QuickNode fallback), mirror pattern of `trading/llm/client.py` fallback chain |
| F.g4 | Reputation formula "+1 per $1 USDC" is arbitrary and uncapped — whale can dominate leaderboard | Cap per-day boost per agent (e.g., max +50 Elo/day from tips); log-scale beyond $X; decay over 30 days |
| F.g5 | Sybil / wash-tipping — agent owner tips themselves from fresh wallets | Require wallet to have ≥N prior mainnet txs or ≥$M USDC balance; flag self-tips (owner wallet in `users.wallet_addresses`) and zero them; public audit log of all tips |
| F.g6 | OFAC sanctions screening on receiving address not addressed | Chainalysis/TRM Labs API check on `sender_address` before crediting; reject sanctioned-wallet tips; log for compliance |
| F.g7 | `agent_registry(name)` FK target — table name not confirmed in codebase (we have `identity.agents` and Elo tables scattered) | F.01 resolves: FK points to the authoritative agent table after grep; if it's `identity.agents(name)`, update schema |
| F.g8 | Wallet library choice left as "e.g., ConnectKit / Web3Modal / wagmi" | Pick one: **wagmi + RainbowKit** (most mature, supports MetaMask/Coinbase/Phantom). No "e.g." in shipped code. |

| Seq | Title | Depends on | Parallel | Effort |
|-----|-------|------------|----------|--------|
| F.01 | `crypto_tips` table + confirm agent FK target + migrations across all 3 schema sources | A.01 | No | 4-6h |
| F.02 | Backend verify endpoint (`POST /api/v1/tips/verify`) with all 5 security checks + N-confirmation wait + `ON CONFLICT` race guard | F.01 | No | 10-16h |
| F.03 | RPC fallback chain (Alchemy primary, QuickNode secondary) + OFAC sanctions screening call | F.02 | Yes | 6-10h |
| F.04 | Reputation boost integration — capped formula, decay, self-tip zeroing; wires into existing Elo/reputation store | F.02 | Yes | 6-10h |
| F.05 | Reorg sweep job — periodic verification of recent `crypto_tips` rows; revert Elo on invalidation | F.02 | Yes | 4-8h |
| F.06 | Frontend: wagmi + RainbowKit setup; `<TipAgentButton>`; tip modal; tx submission + verification polling UI | F.02 | Yes | 16-24h |
| F.07 | Unit + integration tests: signature verification edge cases, race handling, reorg sweep, OFAC block, self-tip zero | F.02-F.06 | No | 8-12h |
| F.08 | OFAC/tipping compliance memo (`docs/compliance/tipping-memo.md`) — short external review on sanctions posture + Howey-test sanity check on reputation boosts | — | Yes | 2-4h ours + external |

**Track F total: 56-90h** (spec's "lean" framing implied ~30-40h; revision accounts for reorg + Sybil + OFAC work missing from original).

**Not blocking anything else** — Track F is an independent perk. Can ship after Tracks A + C, or be deferred indefinitely without affecting Signal API / Agent Auth API revenue.

**Won't be kept from original spec:**
- The self-review claim of "no TBDs" — it had at least 8 (gaps above)
- The uncapped linear reputation formula
- The single-RPC-provider assumption
- The implication that verification is a one-shot check rather than a confirmation-based credit

---

#### Track E: Phase 0 GTM (gates C.12 compliance and all paid launch)

| Seq | Title | Depends on | Parallel | Effort |
|-----|-------|------------|----------|--------|
| E.01 | Landing page + waitlist email capture (`/pricing` shell with "Notify me" CTAs per tier) | — | Yes | 4-6h |
| E.02 | Pricing validation — 5 customer discovery calls; willingness-to-pay log in `docs/gtm/pricing-interviews.md` | E.01 | No | 8-10h |
| E.03 | Competitor scan — feature/price table in `docs/gtm/competitor-scan.md` covering CoinSignals, TradingView alerts, Arkham, Nansen, Dune, whalemap | — | Yes | 4-6h |
| E.04 | First-10-customers plan — named channels + outreach doc in `docs/gtm/first-10-customers.md` (Bittensor Discord, r/algotrading, X, existing network) | E.02, E.03 | No | 4-6h |
| E.05 | Legal/compliance memo — external review answering "is selling signals financial advice under our setup?" and "required disclaimers?"; doc at `docs/compliance/signals-memo.md` | — | Yes | 4-6h ours + external review |

**Track E total: 24-34h** (ours; external review cost/time not included).

**Gate:** C.12 blocks on E.02 **and** E.05. Paid launch blocks on all of Track E plus Tracks A-D.

---

#### Reconciled critical path

```
A.01 (users + tier)
  ├─ A.02 (stripe_events)
  │    └─ B.02 (webhook dispatcher) ── B.03 (tests)
  ├─ B.01 (registry + checkout)
  │    ├─ C.02, D.02 (product registration, parallel)
  │    │    └─ C.03, D.03 (product webhooks)
  │    └─ C.10, D.10 (unified /pricing + dashboards)
  ├─ C.01 (signals tables)
  │    ├─ C.04 (keys) ── C.05/06/07/08/09 (parallel)
  │    └─ C.11 (tests) ── C.12 (compliance gate)
  └─ D.01 (auth_tokens)
       ├─ D.04 (agents) ── D.05 (tokens) ── D.06 (verify)
       │    └─ D.07, D.08, D.09 (parallel)
       └─ D.11 (tests)

E.01..E.05 run in parallel with Tracks A-D; E.02 + E.05 gate C.12 and launch.
```

#### Rollup

| Track | Effort |
|-------|--------|
| **T. Personal Capital Proving Ground (top priority — gates everything else)** | **42-68h** |
| A. Platform Foundation | 6-12h |
| B. Shared Billing | 26-38h |
| C. Signal API | 76-124h |
| D. Agent Auth API | 66-106h |
| E. Phase 0 GTM | 24-34h (ours) |
| F. Crypto Tipping (optional perk, non-blocking) | 56-90h |
| **Total (T + A-E required for revenue)** | **240-382h** |
| **Total incl. F** | **296-472h** |

The old `.tmp/tasks/signal-api/` and `.tmp/tasks/agent-auth-api/` JSON trees are retained for reference but **out-of-date**. When regenerating JSON subtasks for `coder-agent`, derive them from the tables above, not from the original trees.
