# PM Arb Signal Feed — v1 Design

**Date:** 2026-04-15
**Status:** Approved (brainstorm complete; implementation plan to follow)
**Owner:** mspeicher
**Related:**
- `project_monetization_architecture` (memory) — parent monetization spec
- `reference_arb_pipeline_startup_gating` (memory) — production arb path
- `project_polymarket_fallback_unreachable` (memory) — current arb engine state
- `project_phase_0_complete` (memory) — Phase 0 strategy expansion gates

---

## 1. Goal

Sell a public, verifiable cross-platform prediction-market arbitrage signal feed to semi-pro quants and small prop desks at **$500/mo flat**, single tier. Paid tier opens **~75 days from spec start** (week 11 — see §10). This is the v1 product on `remembr.dev` and the foundation for two follow-on products:

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

Unauthenticated. Updates every ~10s. Shows:

- Live signal stream (last 50 signals, newest first)
- Each signal annotated with eventual outcome: `filled` / `missed` / `dead-book-skipped`
- Realized PnL ($, closed positions on the $11k personal sleeve)
- Open PnL ($, mark-to-market)
- Cumulative PnL since launch (line chart)
- Signal-to-fill latency histogram

The dashboard *is* the credibility play. If a strategy goes red publicly, we show it. The story is "honest tracker," not "perfect tracker."

### 3.2 Subscriber API — `GET /api/v1/feeds/arb/signals`

Authenticated via existing identity store + new scope `read:feed_arb`. Reuses `require_scope` dependency, rate limiter, and audit middleware already in place.

**Query params:**
- `since` (ISO-8601 timestamp, required) — return signals emitted at or after this timestamp
- `limit` (int, default 100, max 500)

**Response shape (per signal):**
```json
{
  "signal_id": "arb_2026-04-15T14:32:00Z_kxelec_pres-trump",
  "ts": "2026-04-15T14:32:00Z",
  "pair": {
    "kalshi": {"ticker": "KXPRES-2024-DJT", "side": "YES"},
    "polymarket": {"token_id": "0xabc...", "side": "NO"}
  },
  "edge_cents": 4.2,
  "size_hint_usd": 250,
  "expires_at": "2026-04-15T14:37:00Z",
  "confidence": 0.78
}
```

Polling cadence assumption: ~30s. Rate limit set accordingly (default tier: 240 req/hr).

### 3.3 Landing page — `remembr.dev/feeds/arb`

Single page. Sections: pitch, sample signals (5 most recent from public dashboard), embedded PnL chart, design-partner CTA before launch ("apply for free 60-day access"), Stripe checkout button after launch.

## 4. Architecture

Four components, all on existing trading-engine infra (FastAPI port 8080, Postgres, identity store).

```
SignalBus (existing)
   ├─→ existing arb executor ($11k sleeve, exists)
   └─→ feed_publisher (new)
         └─→ feed_arb_signals table (new)
                ├─→ /feeds/arb/live  (public dashboard, no auth)
                └─→ /api/v1/feeds/arb/signals  (auth: read:feed_arb)

Stripe webhook → /api/v1/billing/stripe/webhook → identity_store.provision_subscription()
```

### 4.1 Components

| Component | Description | Files (anticipated) |
|---|---|---|
| `feed_publisher` | Subscribes to existing `SignalBus` for `cross_platform_arb` events, persists to `feed_arb_signals` table | `trading/feeds/publisher.py` |
| `feed_arb_signals` table | Append-only signal log + outcome tags | `_INIT_DDL` + `init-trading-tables.sql` + `_migrations` (per `reference_schema_three_sources` rule) |
| Subscriber API route | `GET /api/v1/feeds/arb/signals` | `trading/api/routes/feeds.py` |
| Public dashboard backend | `GET /api/v1/feeds/arb/public` (no auth, aggregated stats + last-N signals) | `trading/api/routes/feeds.py` |
| Public dashboard frontend | React 19 + Vite, reuse Mission Control patterns | `frontend/src/pages/FeedArbLive.tsx`, `frontend/src/lib/api/feeds.ts` |
| PnL attribution job | Reads broker fills, computes realized/open/cumulative, writes rollup table | `trading/feeds/pnl_attribution.py` |
| Stripe integration | Single product, single recurring price, customer portal, webhook handler | `trading/api/routes/billing.py`, `trading/billing/stripe_client.py` |
| Landing page | Static-ish, served by frontend | `frontend/src/pages/FeedArbLanding.tsx` |

### 4.2 Database schema

Two new tables:

**`feed_arb_signals`** (append-only)
```sql
CREATE TABLE feed_arb_signals (
    signal_id TEXT PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    pair_kalshi_ticker TEXT NOT NULL,
    pair_kalshi_side TEXT NOT NULL,
    pair_poly_token_id TEXT NOT NULL,
    pair_poly_side TEXT NOT NULL,
    edge_cents NUMERIC(10,2) NOT NULL,
    size_hint_usd NUMERIC(12,2) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    confidence NUMERIC(4,3) NOT NULL,
    outcome TEXT,                          -- 'filled' | 'missed' | 'dead_book_skipped' | NULL (pending)
    outcome_set_at TIMESTAMPTZ,
    raw_signal JSONB NOT NULL              -- full original signal for forensics
);
CREATE INDEX idx_feed_arb_signals_ts ON feed_arb_signals(ts DESC);
CREATE INDEX idx_feed_arb_signals_outcome ON feed_arb_signals(outcome) WHERE outcome IS NULL;
```

**`feed_arb_pnl_rollup`** (point-in-time rollups, written by attribution job every ~60s)
```sql
CREATE TABLE feed_arb_pnl_rollup (
    rollup_ts TIMESTAMPTZ PRIMARY KEY,
    realized_pnl_usd NUMERIC(12,2) NOT NULL,
    open_pnl_usd NUMERIC(12,2) NOT NULL,
    cumulative_pnl_usd NUMERIC(12,2) NOT NULL,
    open_position_count INT NOT NULL,
    closed_position_count INT NOT NULL
);
```

Both tables added to **all three** schema sources (`_INIT_DDL`, `init-trading-tables.sql`, `_migrations`) per `reference_schema_three_sources` parity rule.

### 4.3 New scope

Add `read:feed_arb` to the scope vocabulary. Per `feedback`: scope additions require updating `conductor/tracks/agent_identity/spec.md` §3.C *first*.

| Scope | Description |
|---|---|
| `read:feed_arb` | Read access to `/api/v1/feeds/arb/signals` |

This is a read-only scope; existing identity-store provisioning logic handles it.

## 5. PnL attribution

Single source of truth: actual fills from the $11k personal sleeve, queried from the broker (IBKR for equities-side hedges if any; on-chain + Kalshi API for the PM legs themselves).

The attribution job runs every ~60s and:

1. Pulls fills since last rollup from broker/exchange APIs
2. Joins fills back to originating `signal_id` via `client_order_id` tagging (signals must tag their executed orders with `signal_id` — small change to the existing arb executor)
3. Computes realized PnL on closed pairs, open PnL on still-active pairs (mark-to-market against current Kalshi/Polymarket mid-prices)
4. Writes new row to `feed_arb_pnl_rollup`
5. Updates `outcome` field on `feed_arb_signals` for any signal that just filled, expired, or was skipped

Failure mode: if broker API hiccups, skip the rollup tick (don't write a row). Dashboard shows last-good rollup with stale-ts marker after 5 minutes.

## 6. Stripe integration

**Product setup (one-time, in Stripe dashboard):**
- One product: "remembr.dev — Arb Signal Feed"
- Two prices: `$500/mo` (default) and `$300/mo` (founding-member, restricted via promo code)
- Customer portal enabled (let subscribers cancel themselves)

**Server-side flow:**
- `POST /api/v1/billing/stripe/checkout` — create Checkout Session, return URL
- `POST /api/v1/billing/stripe/webhook` — handle `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`
- On `completed`: provision identity-store entry (new agent name = `feed_sub_<stripe_customer_id>`, scope = `read:feed_arb`), email API key
- On `deleted`: revoke scope (don't delete identity record — keep audit trail)
- Webhook handler is **idempotent** (Stripe retries; key on `event.id` deduplication)

**Reconciliation job** runs daily: fetches active Stripe subscriptions, ensures each has a corresponding active scope in identity store. Catches drift from missed webhooks.

**Secrets:** new `STA_STRIPE_SECRET_KEY`, `STA_STRIPE_WEBHOOK_SECRET`, `STA_STRIPE_PRICE_ID_DEFAULT`, `STA_STRIPE_PRICE_ID_FOUNDING` env vars (per `reference_sta_env_var_convention` — config field names match without prefix).

## 7. Failure modes

| Failure | Behavior |
|---|---|
| `feed_publisher` crashes | Last cached signals shown on dashboard with stale-ts marker; subscriber API returns `503` with `Retry-After: 30` |
| Stripe webhook delayed/lost | Idempotent handler + daily reconciliation job catches drift |
| Public dashboard PnL goes red | Show it. Honest tracker is the brand. |
| Identity store misses scope provisioning | Existing admin override path (`POST /api/v1/admin/identity/grant-scope`) covers manual recovery |
| Broker API hiccups during PnL attribution | Skip the rollup tick; dashboard shows stale-ts marker after 5 min |
| Subscriber polls too aggressively | Existing rate limiter rejects with `429`; per-tier limit configured via `get_tier_limit` |

## 8. Testing

**Unit tests** (under `trading/tests/unit/`):
- `feed_publisher` correctly subscribes to SignalBus and writes to table
- `read:feed_arb` scope enforced on subscriber route
- Stripe webhook handler is idempotent (replay same event ID → no duplicate provisioning)
- PnL attribution math (realized vs open, fill matching by `client_order_id`)
- Outcome tagging logic (filled / missed / dead-book-skipped)

**Integration tests** (under `trading/tests/integration/`, real DB):
- End-to-end: signal fires on bus → row appears in table → API returns it with valid scope, rejects without
- Stripe test-mode webhook → identity store provisioned → API call succeeds
- Reconciliation job: orphaned scope (no active sub) gets revoked; missing scope (active sub) gets re-provisioned

**Live smoke** (manual, pre-launch):
- Create paper subscription via Stripe test mode using a real card-test number
- Verify email arrives with API key
- `curl` subscriber endpoint with the key, get signals
- Cancel via customer portal, verify scope revoked within 60s

**Test policy reminders** (per memory):
- No mock-only tests for the publisher path (per `feedback_fallback_integration_tests`, `feedback_integration_tests_mocked`)
- Run from repo root: `cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/ -v --tb=short --timeout=30`
- Use `trading/.venv/bin/python` (not system Python — per `feedback_venv_not_system_python`)

## 9. Build scope and effort

| Component | Effort |
|---|---|
| `feed_arb_signals` + `feed_arb_pnl_rollup` tables (3 schema sources) | 0.5d |
| `feed_publisher` SignalBus subscriber | 0.5d |
| `read:feed_arb` scope (spec update + identity store) | 0.25d |
| Subscriber REST route + rate limit tier | 0.5d |
| Public dashboard backend route | 0.5d |
| PnL attribution job + `client_order_id` signal tagging | 1d |
| Public dashboard frontend page | 1.5d |
| Stripe integration (checkout + webhook + reconciliation) | 1.5d |
| Landing page on `remembr.dev/feeds/arb` | 0.5d |
| Tests (unit + integration + live smoke) | 1d |
| **Total** | **~7.75 days** |

## 10. Launch sequence

| Week | Milestone |
|---|---|
| 0 (this week) | Tables, publisher, scope, subscriber API, dashboard backend |
| 1 | PnL attribution + dashboard frontend; Stripe in test mode |
| 2 | Landing page + dashboard public; DM 5 design-partner candidates |
| 2–10 (60 days) | Free design-partner access; weekly feedback calls; iterate API based on real usage |
| 11 (~75 days) | Open paid tier ($500/mo default, $300/mo founding-member promo) |

**Forcing function:** the paid-tier date is a hard commitment on `remembr.dev` from week 2 forward. No extensions.

## 11. Out of scope for v1

Explicitly parked (each is a future spec):

- Webhook delivery (v2 — premium tier)
- SN8 consensus feed (separate product for audience C)
- Tiered pricing (Bronze/Silver/Gold) — premature without webhook to gate
- Position-sizing recommendations beyond `size_hint_usd`
- Multi-asset coverage (futures, equities, crypto) — PM-only for v1
- PnL share / performance fees (non-starter for signal products)
- Mobile/SDK clients
- Backtesting access (separate product if there's demand)
- Discord/Telegram delivery (wrong audience)

## 12. Open questions

None blocking. Resolved during brainstorm:

- ✓ Audience: B (semi-pro quants), with C as later separate product
- ✓ Product: PM arb signal feed only for v1
- ✓ Credibility: hybrid (public dashboard + 5 design partners, 75-day window)
- ✓ Delivery: REST polling, payload schema fixed
- ✓ Pricing: $500/mo flat single tier, $300/mo founding-member promo

## 13. Success criteria

v1 ships successfully when:

1. Public dashboard live at `remembr.dev/feeds/arb/live` showing real signals + real PnL from $11k sleeve
2. ≥3 design partners actively polling the subscriber API during the free window
3. Paid tier opens on schedule (week 11)
4. ≥1 paying customer within 30 days of paid-tier opening
5. No silent failures in PnL attribution (gaps in `feed_arb_pnl_rollup` < 5% of expected ticks)

Customer #1 within 30 days of opening is the gate that unlocks the next product (#5 hosted MemPalace). Without it, we revisit the audience hypothesis before scaling further.
