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
