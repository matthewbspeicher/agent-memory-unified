# PM Arb Signal Feed — v1 Design (rev 2)

**Date:** 2026-04-15 (rev 2 same day, post-review)
**Status:** Approved (brainstorm + self-review complete; implementation plan to follow)
**Owner:** mspeicher
**Related:**
- `project_monetization_architecture` (memory) — parent monetization spec
- `project_remembr_dev_income_tracks` (memory) — 3-track income plan; this is track #3
- `reference_arb_pipeline_startup_gating` (memory) — production arb path
- `project_polymarket_fallback_unreachable` (memory) — current arb engine state
- `project_phase_0_complete` (memory) — Phase 0 strategy expansion gates

---

## 1. Goal

Sell a public, verifiable cross-platform prediction-market arbitrage signal feed to semi-pro quants and small prop desks at **$500/mo flat**, single tier. Paid tier opens **week 11 (~75 days from spec start)**. This is the v1 product on `remembr.dev` and the foundation for two follow-on products:

- **v2 — webhook delivery upgrade tier** (paid premium feature)
- **Separate product — SN8 consensus feed** for the Bittensor validator audience (audience C)

This spec covers v1 only.

## 2. Audience

**Primary (v1):** semi-pro quants, individual algo traders with $250k–$1M books, small prop desks. They will:

- Trust live attributable PnL above all else
- Integrate via REST/HTTP, not Discord or web UI
- Treat $500/mo as a normal data-feed line item
- Look at the public dashboard before they pay
- Want signal-to-fill slippage transparency

**Explicitly not v1 audience:** retail traders, casual crypto users, other Bittensor validators. The retail market is crowded with low-quality signal sellers and would require a different product (Discord, lower price, more support, higher churn).

## 3. Product surface

### 3.1 Public dashboard — `remembr.dev/feeds/arb/live`

Unauthenticated. Updates every ~10s. Shows three concurrent PnL exhibits plus the signal stream:

**PnL exhibits (the credibility play):**
1. **Realized on $11k personal sleeve: $X** — actual broker fills, no scaling. The honest tracker.
2. **Scaled to $250k notional: $Y** — model projection at proportional sizing. **Always labeled:** "model projection at proportional sizing — assumes available book depth, no transaction-cost adjustment beyond observed slippage." Lets buyers reason about whether the strategy clears the $500/mo at their book size.
3. **Backtest envelope** (last 90 days, daily PnL bars) — historical context behind the live tracker.

**Signal stream:** last 50 signals, newest first, each annotated with eventual outcome: `filled` / `missed` / `dead_book_skipped` / `pending`. Plus signal-to-fill latency histogram.

**Why scaled view matters:** $11k at typical PM-arb returns produces ~$140/mo realized PnL — selling against that alone makes the price tag look absurd. Scaled view shows the *strategy economics*, not the *test sleeve economics*. Real sleeve stays prominent so the honesty story holds.

If a strategy goes red publicly, we show it. The story is "honest tracker," not "perfect tracker."

### 3.2 Subscriber API — `GET /api/v1/feeds/arb/signals`

Authenticated via existing identity store + new scope `read:feeds.arb`. Reuses `require_scope` dependency, rate limiter, and audit middleware already in place.

**Query params:**
- `since` (ISO-8601 timestamp, required) — return signals emitted at or after this timestamp
- `limit` (int, default 100, max 500)

**Response shape:**
```json
{
  "signals": [
    {
      "signal_id": "01HXX0K9TQVS5N7E2QF7P9V8XQ",
      "ts": "2026-04-15T14:32:00Z",
      "pair": {
        "kalshi": {"ticker": "KXPRES-2024-DJT", "side": "YES"},
        "polymarket": {"token_id": "0xabc...", "side": "NO"}
      },
      "edge_cents": 4.2,
      "max_size_at_edge_usd": 1850,
      "expires_at": "2026-04-15T14:37:00Z"
    }
  ],
  "next_since": "2026-04-15T14:35:00Z",
  "truncated": false
}
```

**Field semantics:**
- `signal_id` — opaque ULID, monotonic-ish, no embedded internals. Stable forever; clients should dedup on this.
- `edge_cents` — gross edge at signal emission, before fees and slippage.
- `max_size_at_edge_usd` — the smaller of (Kalshi-leg orderbook depth at quoted edge, Polymarket-leg depth at quoted edge). What *the market* will absorb at this edge, not a recommended position size. Customers size against their own book and risk tolerance.
- `expires_at` — signal validity horizon. API returns historical signals past their `expires_at`; clients filter if they want only live ones.
- `next_since` — set when `truncated=true` (response hit `limit`). Client should immediately re-poll with `since=next_since` to backfill. When `truncated=false`, `next_since` echoes the latest returned `ts` (or the request's `since` if response is empty).

**Polling contract:**
- Recommended cadence: 30s
- Rate limit: **600 req/hr per subscription** (10 req/min, 6× headroom over recommended cadence)
- One client per subscription. A subscription making concurrent polls from 3 bots will hit the limit.
- Clients **must dedup on `signal_id`** for overlapping `since` windows.

**Removed from v1 payload (vs. rev 1):**
- `confidence` — dropped. Without published calibration data (reported vs realized by decile), it's noise. Will return in v2 only with calibration commitment.
- `size_hint_usd` — replaced by `max_size_at_edge_usd`. The hint was meaningless to a $1M book; orderbook depth at edge is universally useful.

### 3.3 Landing page — `remembr.dev/feeds/arb`

Single page. Sections: pitch, sample signals (5 most recent from public dashboard), embedded PnL chart (all 3 exhibits), design-partner CTA before launch ("apply for free 60-day access"), Stripe checkout button after launch. CORS for the public-fetch JSON pinned to `remembr.dev` (and `localhost:3000` for dev).

## 4. Architecture

Components, all on existing trading-engine infra (FastAPI port 8080, Postgres, identity store).

> **Implementation reconciliation (2026-04-16):** the publisher source is the existing **`EventBus` topic `arb.spread`** (not `SignalBus` as this doc originally described). `cross_platform_arb.py:232-254` already publishes `arb.spread` with the full payload needed, and `ArbExecutor` already consumes it. Two independent subscribers, one topic — the `SignalBus` is not wired for cross-platform arb, so using `EventBus` avoids a wholly-new registration path. See plan Alt-4 and [phase-b-findings.md §B6](../../feeds/arb/phase-b-findings.md).

```
EventBus (existing) — topic "arb.spread"
   ├─→ ArbExecutor ($11k sleeve, exists) — tags fills with signal_id (see §5)
   └─→ feed_publisher (new)
         └─→ feed_arb_signals table (new)
                ├─→ /api/v1/feeds/arb/public  (no auth — dashboard)
                └─→ /api/v1/feeds/arb/signals  (auth: read:feeds.arb)

PnL attribution job (new, every 60s)
   ├─→ pulls fills from broker APIs by signal_id
   └─→ writes feed_arb_pnl_rollup (real + scaled) + updates outcome on signals

Stripe webhook → /api/v1/billing/stripe/webhook
   └─→ idempotent (stripe_processed_events)
   └─→ identity_store provisions scope read:feeds.arb on agent sub_<sub_id>

Hourly reconciliation job → fixes missed webhook drift
Manual /api/v1/admin/billing/reconcile → ops escape hatch

Monitoring → freshness SLI, alert on stale publisher / stale rollup
```

### 4.1 Components

| Component | Description | Files (anticipated) |
|---|---|---|
| `feed_publisher` | Subscribes to existing `EventBus` topic `arb.spread`, re-applies the `CostModel.should_execute` gate, persists to `feed_arb_signals` | `trading/feeds/publisher.py` (shipped in `c54d3ab`) |
| `feed_arb_signals` table | Append-only signal log + outcome tags | **Two** schema sources in practice: `init_db_postgres()` (prod, `TIMESTAMPTZ/NUMERIC/JSONB`) + `init-trading-tables.sql` (bootstrap snapshot). `_INIT_DDL` SQLite block is **not** used for these tables on Postgres — see §4.2 reconciliation below. |
| `feed_arb_pnl_rollup` table | Real + scaled PnL snapshots every 60s | same two sources |
| `stripe_processed_events` table | Idempotency keys for Stripe webhook | same two sources |
| `signal_order_map` table | `order_hash → signal_id` mapping for Polymarket (no round-trip of `client_order_id` available) | same two sources; populated by `OrderManager` after `clob.create_order` |
| Subscriber API route | `GET /api/v1/feeds/arb/signals` | `trading/api/routes/feeds.py` |
| Public dashboard backend | `GET /api/v1/feeds/arb/public` (no auth, aggregated stats + last-N signals) | `trading/api/routes/feeds.py` |
| Public dashboard frontend | React 19 + Vite, reuse Mission Control patterns | `frontend/src/pages/FeedArbLive.tsx`, `frontend/src/lib/api/feeds.ts` |
| `signal_id` plumbing through ArbExecutor | Tag every Kalshi+Polymarket order with originating `signal_id` so fills can be joined back | `trading/agents/cross_platform_arb/executor.py` (and its Polymarket execution path) |
| PnL attribution job (real) | Reads broker fills, computes realized/open, writes real-sleeve rollup | `trading/feeds/pnl_attribution.py` |
| PnL attribution job (scaled) | Projects scaled-to-$250k PnL using observed slippage + book depth | same file |
| Stripe checkout + webhook | Single product, single recurring price, customer portal, idempotent webhook | `trading/api/routes/billing.py`, `trading/billing/stripe_client.py` |
| Hourly reconciliation + manual `/api/v1/admin/billing/reconcile` | Catches missed webhooks; manual ops escape hatch | `trading/billing/reconciliation.py` |
| Monitoring / freshness alerts | Publisher write-rate, rollup gap detector | `trading/feeds/monitoring.py` (new) |
| Landing page | Static-ish, served by frontend | `frontend/src/pages/FeedArbLanding.tsx` |

### 4.2 Database schema

**Four** new tables (`feed_arb_signals`, `feed_arb_pnl_rollup`, `stripe_processed_events`, `signal_order_map`). Schema home is `init_db_postgres()` in `trading/storage/db.py` (Postgres-native `TIMESTAMPTZ`/`NUMERIC`/`JSONB`) plus a mirror in `scripts/init-trading-tables.sql` for bootstrap. **Not** in `_INIT_DDL` — earlier versions duplicated them there with SQLite types (`TEXT`/`REAL`) and `executescript` silently landed them with the wrong types, causing the explicit native blocks to no-op with `CREATE TABLE IF NOT EXISTS`. See [phase-b-findings.md](../../feeds/arb/phase-b-findings.md) B-extra. (SQLite-specific declarations exist in `init_db()` for unit-test fixtures only, with TEXT/REAL since type precision doesn't matter in-memory.)

The `reference_schema_three_sources` rule referenced in rev 1 is superseded: `trading/storage/migrations.py` is deprecated per its own header; two sources remain in practice.

**`feed_arb_signals`** (append-only)
```sql
CREATE TABLE feed_arb_signals (
    signal_id TEXT PRIMARY KEY,            -- ULID
    ts TIMESTAMPTZ NOT NULL,
    pair_kalshi_ticker TEXT NOT NULL,
    pair_kalshi_side TEXT NOT NULL,
    pair_poly_token_id TEXT NOT NULL,
    pair_poly_side TEXT NOT NULL,
    edge_cents NUMERIC(10,2) NOT NULL,
    max_size_at_edge_usd NUMERIC(12,2) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    outcome TEXT,                          -- 'filled' | 'missed' | 'dead_book_skipped' | NULL (pending)
    outcome_set_at TIMESTAMPTZ,
    raw_signal JSONB NOT NULL              -- full original signal for forensics
);
CREATE INDEX idx_feed_arb_signals_ts ON feed_arb_signals(ts DESC);
CREATE INDEX idx_feed_arb_signals_pending ON feed_arb_signals(ts) WHERE outcome IS NULL;
```

**Outcome enum semantics:**
- `filled` — both legs executed within `expires_at`. PnL attributable.
- `missed` — at least one leg failed to fill before `expires_at` (price moved, latency, partial fill abandoned).
- `dead_book_skipped` — executor evaluated the signal at fill time and found < `max_size_at_edge_usd` available at the quoted edge on at least one leg's orderbook (executor never placed the order). Set by the executor at decision time, not post-hoc.
- `NULL` — pending: signal emitted, outcome not yet determined (within `expires_at` window).

**`feed_arb_pnl_rollup`** (point-in-time rollups, real + scaled)
```sql
CREATE TABLE feed_arb_pnl_rollup (
    rollup_ts TIMESTAMPTZ PRIMARY KEY,
    -- real ($11k sleeve)
    realized_pnl_usd NUMERIC(12,2) NOT NULL,
    open_pnl_usd NUMERIC(12,2) NOT NULL,
    cumulative_pnl_usd NUMERIC(12,2) NOT NULL,
    open_position_count INT NOT NULL,
    closed_position_count INT NOT NULL,
    -- scaled ($250k notional projection)
    scaled_realized_pnl_usd NUMERIC(14,2) NOT NULL,
    scaled_open_pnl_usd NUMERIC(14,2) NOT NULL,
    scaled_cumulative_pnl_usd NUMERIC(14,2) NOT NULL,
    scaling_assumption TEXT NOT NULL       -- e.g. "linear-to-250k-with-observed-slippage-v1"
);
```

**`stripe_processed_events`** (webhook idempotency)
```sql
CREATE TABLE stripe_processed_events (
    event_id TEXT PRIMARY KEY,             -- Stripe event.id
    event_type TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    result TEXT NOT NULL                   -- 'ok' | 'noop' | 'error:<msg>'
);
```

### 4.3 New scope (namespaced)

Add `read:feeds.arb` to the scope vocabulary. Per CLAUDE.md: scope additions require updating `conductor/tracks/agent_identity/spec.md` §3.C *first*.

| Scope | Description |
|---|---|
| `read:feeds.arb` | Read access to `/api/v1/feeds/arb/signals` |

**Namespace decision (locked):** `read:feeds.<feed_name>`. Future scopes will follow the pattern: `read:feeds.sn8`, `read:feeds.arb.webhook` (premium tier in v2). A `read:feeds.*` wildcard is reserved for future bundle tiers; not implemented in v1.

This is a read-only scope; existing identity-store provisioning logic handles it.

## 5. PnL attribution

Single source of truth: actual fills from the $11k personal sleeve, joined to signals via `signal_id`-tagged orders.

### 5.1 Signal → fill tagging (load-bearing)

Every order placed by ArbExecutor must carry the originating `signal_id` so fills can be matched back. Two execution paths, two mechanisms:

- **Kalshi:** `client_order_id` field on order placement carries `signal_id` directly (Kalshi round-trips it on fills). Standard pattern.
- **Polymarket:** EIP-712 signed orders **do not round-trip a free-text identifier**. Two-step approach:
  1. Maintain an in-memory map `polymarket_order_hash → signal_id` at order-placement time.
  2. On fill events from Polymarket's data API, look up by order hash; persist the resolution to a `signal_order_map` join table for crash-safety.

This is **non-trivial** plumbing through `trading/agents/cross_platform_arb/executor.py` and the Polymarket execution path. Called out as its own line item in §9.

### 5.2 Attribution job

Runs every ~60s and:

1. Pulls fills since last rollup from broker/exchange APIs (Kalshi REST, Polymarket data API at `https://data-api.polymarket.com`)
2. Joins fills back to originating `signal_id` (via Kalshi `client_order_id` or Polymarket order-hash lookup)
3. Computes realized PnL on closed pairs, open PnL on still-active pairs (mark-to-market against current Kalshi/Polymarket mid-prices)
4. Computes **scaled** PnL: each real fill scaled linearly to $250k notional, capped at observed orderbook depth at fill time, with observed slippage carried through proportionally. Scaling assumption versioned in `scaling_assumption` field.
5. Writes new row to `feed_arb_pnl_rollup` (both real and scaled values)
6. Updates `outcome` field on `feed_arb_signals` for any signal that just filled, expired, or was skipped

**Failure mode:** if broker API hiccups, skip the rollup tick (don't write a row). Dashboard shows last-good rollup with stale-ts marker after 5 minutes. Monitoring (§11) alerts on gap > 5 min.

## 6. Stripe integration

**Product setup (one-time, in Stripe dashboard):**
- One product: "remembr.dev — Arb Signal Feed"
- Two prices: `$500/mo` (default) and `$300/mo` (founding-member, restricted via promo code, 12-month lock)
- Customer portal enabled (let subscribers cancel themselves)

**Server-side flow:**
- `POST /api/v1/billing/stripe/checkout` — create Checkout Session, return URL
- `POST /api/v1/billing/stripe/webhook` — handle `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`
- On `completed`:
  1. Insert into `stripe_processed_events` with `event.id` (UNIQUE — duplicate inserts no-op)
  2. Provision identity-store entry (agent name = **`sub_<stripe_subscription_id>`** — keyed on subscription not customer, so future second subscription doesn't collide), scope = `read:feeds.arb`
  3. Manual email API key to customer (see §6.1)
- On `deleted`: revoke scope (don't delete identity record — keep audit trail)
- On `updated`: handle plan changes, pause/resume

**Idempotency:** keyed on `stripe_processed_events.event_id`. Stripe retries are no-ops. Multi-worker safe via UNIQUE constraint.

**Hourly reconciliation job** (was: daily):
- Fetches active Stripe subscriptions
- Ensures each has a corresponding active scope in identity store
- Provisions missing, revokes orphaned (active scope with no Stripe sub)
- Logs drift metrics

**Manual recovery endpoint:** `POST /api/v1/admin/billing/reconcile` (scope `admin`) triggers on-demand reconciliation. Ops escape hatch when a customer reports "I paid but no key arrived."

**Secrets:** new env vars (per `reference_sta_env_var_convention`):
- `STA_STRIPE_SECRET_KEY`
- `STA_STRIPE_WEBHOOK_SECRET`
- `STA_STRIPE_PRICE_ID_DEFAULT`
- `STA_STRIPE_PRICE_ID_FOUNDING`

### 6.1 Customer email — manual for v1

No transactional email provider in v1. For the first ~10 customers (5 design partners + ~5 founding members during the 75-day window):

- Webhook handler logs new provisioning to a dedicated `new_subscription_alerts` log channel (and writes a row to identity store)
- Owner manually copies the API key into a personal email to the customer
- Operational SLA: respond within 4 business hours

**When to automate:** before scaling past 20 customers. Pick provider then (likely Postmark or AWS SES). Out of scope for v1.

**Why this is OK:** at $500/mo per customer × 10 customers = $5k/mo MRR, the 30 minutes per onboarding is not the bottleneck. Premature email automation costs more than it saves until volume grows.

## 7. Failure modes

| Failure | Behavior |
|---|---|
| `feed_publisher` crashes | Last cached signals shown on dashboard with stale-ts marker; subscriber API returns `503` with `Retry-After: 30`; monitoring alerts after 15 min of zero writes while arb_executor is running |
| Stripe webhook delayed/lost | Idempotent handler + hourly reconciliation job catches drift; manual `/admin/billing/reconcile` for ops escape |
| Public dashboard real PnL goes red | Show it. Honest tracker is the brand. Scaled view + backtest envelope provide context. |
| Identity store misses scope provisioning | Hourly reconciliation auto-recovers within 60 min; admin override path for faster recovery |
| Broker API hiccups during PnL attribution | Skip the rollup tick; dashboard shows stale-ts marker after 5 min; monitoring alert fires |
| Subscriber polls too aggressively | Existing rate limiter rejects with `429`; per-subscription limit 600/hr |
| Polymarket execution path broken | **Step 0 must verify before feed work begins** — see §10.0 |
| Signal fires but no fill matches within `expires_at` | Outcome set to `missed`; visible on dashboard; PnL impact = 0 |
| `signal_id` lookup fails on Polymarket fill | Log + emit `attribution.unmatched_fill` metric; rollup proceeds without that fill (under-counts real PnL but doesn't crash) |

## 8. Testing

**Unit tests** (under `trading/tests/unit/`):
- `feed_publisher` correctly subscribes to SignalBus and writes to table
- `read:feeds.arb` scope enforced on subscriber route (and rejected without)
- Stripe webhook handler is idempotent (replay same event ID → single provisioning, second insert is noop)
- PnL attribution math: realized vs open, fill matching by `client_order_id` (Kalshi) and order-hash (Polymarket)
- Scaled PnL projection math (linear scaling, depth cap, slippage carry-through)
- Outcome tagging logic (filled / missed / dead_book_skipped / pending → terminal transitions only)
- ULID `signal_id` generation is monotonic-ish and unique

**Integration tests** (under `trading/tests/integration/`, real DB):
- End-to-end: signal fires on bus → row appears in table → API returns it with valid scope, rejects without
- `next_since` cursor: emit 600 signals, poll with `limit=500`, verify `truncated=true` + `next_since` set; second poll returns remaining 100 with `truncated=false`
- Stripe test-mode webhook (via recorded event fixtures, see §8.1) → identity store provisioned → API call succeeds
- Reconciliation job: orphaned scope (no active sub) gets revoked; missing scope (active sub) gets re-provisioned; manual `/admin/billing/reconcile` triggers same logic
- CORS: `OPTIONS /api/v1/feeds/arb/public` returns `remembr.dev` and `localhost:3000`, rejects others

**Live smoke** (manual, pre-launch):
- Create paper subscription via Stripe test mode using a real card-test number
- Verify webhook fires, log message appears
- Manually email API key (verifies the manual flow works)
- `curl` subscriber endpoint with the key, get signals
- Cancel via customer portal, verify scope revoked within 60 min (hourly reconciliation) or immediately (webhook)

### 8.1 Stripe testing infrastructure

CI runners have no public network path for Stripe webhook delivery. Two-prong approach:

- **Local dev:** `stripe-cli listen --forward-to localhost:8080/api/v1/billing/stripe/webhook` for end-to-end testing during dev
- **CI:** recorded event fixtures (JSON payloads captured from a real `stripe-cli trigger` run) committed under `trading/tests/fixtures/stripe/`. Tests POST these to the webhook handler with valid signatures (using `STA_STRIPE_WEBHOOK_SECRET=<test_secret>`)

**Test policy reminders** (per memory):
- No mock-only tests for the publisher path (per `feedback_fallback_integration_tests`, `feedback_integration_tests_mocked`)
- Run from repo root: `cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/ -v --tb=short --timeout=30`
- Use `trading/.venv/bin/python` (not system Python — per `feedback_venv_not_system_python`)

## 9. Build scope and effort

| Component | Effort | Notes |
|---|---|---|
| **Step 0: verify Polymarket execution path** | gating | Acceptance: ≥5 real cross-platform arb trades filled end-to-end on $11k sleeve in last 7 days. If <5, **repair becomes prerequisite work, not part of this spec's effort budget.** |
| `feed_arb_signals` + `feed_arb_pnl_rollup` + `stripe_processed_events` tables (3 schema sources each) | 0.5d | |
| `feed_publisher` SignalBus subscriber | 0.5d | |
| `read:feeds.arb` scope (spec update + identity store) | 0.25d | Spec update first per CLAUDE.md |
| Subscriber REST route + `next_since` cursor + rate limit tier (600/hr) | 0.75d | |
| Public dashboard backend route (with CORS) | 0.5d | |
| `signal_id` plumbing through ArbExecutor (Kalshi `client_order_id` + Polymarket order-hash map) | 0.5d | The Polymarket half is the interesting bit |
| PnL attribution job — real fills, realized/open math | 1.0d | |
| PnL attribution job — scaled projection (linear-to-$250k with depth cap + slippage carry) | 1.0d | New in rev 2 |
| Public dashboard frontend page (3 PnL exhibits + signal stream + latency histogram) | 2.0d | Up from 1.5d for scaled view |
| Stripe integration (checkout + idempotent webhook + manual recovery endpoint) | 1.5d | |
| Hourly reconciliation job | 0.25d | |
| Monitoring/alerting (freshness SLI for publisher + rollup gap) | 0.5d | New in rev 2 |
| Landing page on `remembr.dev/feeds/arb` | 0.5d | |
| Tests (unit + integration + recorded Stripe fixtures + live smoke) | 1.0d | |
| **Total** | **~10.75 days** | Up from rev 1's 7.75d |

**Effort growth rationale:** rev 1 underestimated PnL attribution (missed scaled view + Polymarket order-hash plumbing), missed monitoring entirely, and absorbed Stripe idempotency table without budget. The 3-day delta is real, not padding.

## 10. Launch sequence

### 10.0 Step 0 — Polymarket execution gate (week -1)

**Before any feed work begins**, verify the production arb path actually executes end-to-end:

- Acceptance criterion: **≥5 real cross-platform arb trades filled** (both Kalshi + Polymarket legs) on the $11k sleeve in the last 7 days
- If <5: investigate, repair (separate effort), do not start feed work until satisfied
- If ≥5: proceed to week 0

Without this gate, the dashboard's credibility hook (real fills → real PnL) is structurally blocked.

### 10.1 Build sequence (assumes Step 0 passes)

| Week | Milestone |
|---|---|
| 0 (this week) | Three tables, publisher, scope, subscriber API + cursor, dashboard backend, `signal_id` plumbing |
| 1 | PnL attribution (real + scaled) + dashboard frontend (3 exhibits); Stripe integration in test mode; monitoring/alerting |
| 2 | Landing page + dashboard public; DM 5 design-partner candidates; founding-member promo code created |
| 2–10 (60 days) | Free design-partner access; weekly feedback calls; iterate API based on real usage; fix any production bugs surfaced |
| 10 | **Polish week** (1 week buffer between design-partner window ending and paid-tier opening): finalize landing-page copy, compliance review (see §10.2), verify monitoring is paging on real failures, test Stripe production mode end-to-end |
| 11 (~75 days) | Open paid tier ($500/mo default, $300/mo founding-member promo) |

**Forcing function:** the paid-tier date is a hard commitment on `remembr.dev` from week 2 forward. No extensions.

### 10.2 Week 10 compliance checklist

Selling signals against a CFTC-regulated venue (Kalshi) to third parties may constitute investment advice or commodity trading advice. **Before paid-tier opens:**

- Review the landing page and signal payload with a securities-lawyer consult (one-time, ~$500–1500). Specifically: are we an "advisor," a "data provider," or neither?
- Add appropriate disclaimers ("for informational purposes only," "not investment advice," "past performance does not guarantee future results")
- Confirm Kalshi ToS allows redistribution of derived signals (they do, but verify the latest)
- Confirm Polymarket ToS likewise
- Decide entity structure (sole prop is fine for v1 revenue scale; LLC if/when scaling to #5)

This is not a code task; it's an explicit go/no-go gate for week 11.

## 11. Monitoring and alerting

Public-facing paid product needs a freshness SLI with numeric targets. Wired into the existing alerting infrastructure (Slack/email — pick whichever is already configured).

**SLIs:**
| Indicator | Target | Alert threshold |
|---|---|---|
| `feed_publisher` write rate | Matches `arb_executor` signal emission rate | 0 publisher writes for >15 min while arb_executor running → page |
| `feed_arb_pnl_rollup` freshness | New row every 60s | Gap > 5 min → page |
| Subscriber API p95 latency | < 200ms | > 500ms for 10 min → warn |
| Subscriber API error rate | < 1% | > 5% for 5 min → page |
| Stripe webhook handler error rate | < 1% (excluding signature mismatches) | > 5% for 5 min → page |
| `STA_STRIPE_ENABLED` flag | `true` in prod by launch day | still `false` 48h before paid-tier open → page. Flag gates the webhook handler at [billing/webhooks.py](../../../trading/api/routes/billing/webhooks.py); prior handler was unsafe (unsigned-JSON tier grants) and is disabled by default pending the §6 rebuild. Shipped in `5255235`. |
| Reconciliation job successful run | Hourly | Missed run for 3 consecutive hours → warn |
| Polymarket fill `signal_id` match rate | > 95% | < 80% for 1 hr → warn (suggests order-hash map breakage) |

**Dashboards:** lightweight ops dashboard at `localhost:3000/admin/feeds/arb-ops` (admin scope), separate from the public dashboard. Shows the SLIs above, last 24h.

## 12. Out of scope for v1

Explicitly parked (each is a future spec):

- Webhook delivery (v2 — premium tier, scope `read:feeds.arb.webhook`)
- SN8 consensus feed (separate product for audience C)
- Tiered pricing (Bronze/Silver/Gold) — premature without webhook to gate
- Position-sizing recommendations
- Multi-asset coverage (futures, equities, crypto) — PM-only for v1
- PnL share / performance fees (non-starter for signal products)
- Mobile/SDK clients
- Backtesting access (separate product if there's demand)
- Discord/Telegram delivery (wrong audience)
- Transactional email provider (manual for first 10 customers; pick provider before scaling past 20)
- `confidence` score in payload (returns in v2 with calibration commitment)
- `read:feeds.*` wildcard scope (reserved for future bundle tiers)
- Calibration publishing (reported vs realized confidence by decile) — only if confidence returns

## 13. Open questions

None blocking. Resolved during brainstorm + self-review:

- ✓ Audience: B (semi-pro quants), with C as later separate product
- ✓ Product: PM arb signal feed only for v1
- ✓ Credibility: hybrid (public dashboard + 5 design partners, 75-day window)
- ✓ Delivery: REST polling, payload schema fixed
- ✓ Pricing: $500/mo flat single tier, $300/mo founding-member promo
- ✓ Scope namespace: `read:feeds.arb` (namespaced)
- ✓ Polymarket gate: explicit Step 0 (≥5 real fills in last 7 days)
- ✓ PnL view: real + scaled overlay + backtest envelope
- ✓ Confidence + size hint: dropped / replaced with `max_size_at_edge_usd`
- ✓ Email: manual for first 10, no provider in v1

## 14. Success criteria

v1 ships successfully when:

1. Public dashboard live at `remembr.dev/feeds/arb/live` showing real signals + 3 PnL exhibits (real $11k, scaled $250k, backtest envelope)
2. ≥3 design partners actively polling the subscriber API during the free window
3. Compliance review complete and disclaimers in place (week 10)
4. Paid tier opens on schedule (week 11)
5. ≥1 paying customer within 30 days of paid-tier opening
6. No silent failures: PnL rollup gaps < 5% of expected ticks; Polymarket `signal_id` match rate > 95%

**Pivot plan if customer #1 doesn't land by day 30:**
- Pause paid-tier marketing for 2 weeks
- Schedule 5 follow-up calls with design-partner cohort: what would have made you pay? Was the price the issue, or the product?
- Possible adjustments: lower price floor (test $250/mo), tier the product (free delayed feed + paid real-time), expand audience to C (SN8 validators), or pivot product (sell execution-as-a-service instead of signals)
- Decision point at day 60: continue, pivot, or shelve and move to #5 (hosted MemPalace) regardless

Customer #1 within 30 days remains the gate that unlocks #5. Without it, the audience hypothesis for #5 also needs reconsideration.

## 15. Upstream pipeline prerequisites (2026-04-16)

Four bugs in the upstream pipeline had to be fixed before the publisher could land a single row. Adding here for the audit trail — all shipped, all verified end-to-end. Detailed diagnostics in [phase-b-findings.md](../../feeds/arb/phase-b-findings.md).

| # | Bug | Fix | Commit |
|---|---|---|---|
| A0.1 | `arb_spread_observations.observed_at` column missing in prod Postgres; `SpreadStore.record()` INSERTs silently failing | ALTER TABLE migration in `init_db_postgres()` adds column + two indexes | `5255235` |
| A0.2 | Cron scheduler silently skips `cross_platform_arb` (placeholder returning `None` + warm-restart `interval_or_cron` INTEGER column) | Remove placeholder from `config.py`; read `parameters.cron` JSONB in `runner._reconcile_registry`; pre-register `CrossPlatformArbAgent` class so `AgentsFileSchema` validation passes | `8dc03e4` + `102d5e8` + `5255235` |
| A0.3 | `PostgresDB._convert_datetime_now()` only translated the zero-arg form; `datetime('now', '-N minutes')` modifier form left untranslated → runtime error on `get_top_spreads` / `claim_spread` | Enhanced regex to translate modifier forms to `NOW() - INTERVAL 'N minutes'` | `8dc03e4` |
| A0.4 | `SpreadStore.record()` returned `None` on Postgres (`cursor.lastrowid` not exposed by the wrapper), so even after A0.1 the `arb.spread` publish was gated off | Dual-path `INSERT ... RETURNING id` on Postgres, `cursor.lastrowid` on SQLite | `5255235` |

Plus two collateral fixes in `5255235`: feed/billing table types (TEXT/REAL → TIMESTAMPTZ/NUMERIC/JSONB); `Config.gemini_api_key` flat-field shim; `/stripe/webhooks` disabled behind `STA_STRIPE_ENABLED=true` (see §11).

**Gate:** no paid-tier launch without all four fixes in place and verified. All four shipped and green as of 2026-04-16. Publisher lands rows end-to-end (POST /agents/cross_platform_arb/scan → 11+ rows in `feed_arb_signals`).

## 16. Host topology (v1 monolithic, relocatable)

v1 ships as a monolith: publisher, subscriber API, and public route all live in the existing trading-engine FastAPI process on port 8080. This is intentional for the week-11 launch and deliberately **relocatable** — the new direction (see `project_local_first_direction` memory) is to split the publisher onto a local laptop (next to the strategies that emit `arb.spread`) and the paid-subscriber routes onto the web host (so `remembr.dev` can terminate HTTPS properly for paid traffic).

To keep v1 monolithic without foreclosing the split:

- **Publisher writes to a table.** No in-process handoff between publisher and routes; the DB is the contract.
- **Route handlers are SELECT-and-shape.** No app-state caching inside route handlers; no EventBus subscription in the routes; no DB-side triggers.
- **Public route cache lives on Redis,** not a Python module-level dict. Redis is reachable from either host. `feeds.py` `PUBLIC_CACHE_TTL_SECONDS = 10` and `_PUBLIC_CACHE_KEY` are the cache seam.
- **Prometheus counter names are stable across hosts.** `feed_arb_signals_published_total`, `feed_arb_public_cache_hits_total`, etc. keep their identity when the route moves.

When the split happens, lifting `feeds.py` and `feeds/publisher.py` to separate services is a configuration change, not a rewrite. No plan in this doc for the split itself — that's future work gated on #5 (hosted MemPalace) and audience-C maturity.

## ADR-0008 event types (appendix)

Appending to the canonical event-type list in [docs/adr/0008-structured-logging-convention.md](../../adr/0008-structured-logging-convention.md):

- `feed.publish` — FeedPublisher wrote a row to `feed_arb_signals`
- `feed.public_query` — `/api/v1/feeds/arb/public` served a response (reserved; wire when helpful)
- `feed.subscriber_query` — `/api/v1/feeds/arb/signals` served a response (reserved; wire when helpful)
