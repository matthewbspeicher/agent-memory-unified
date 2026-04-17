# Feed Arb — Alert Runbook

Operational response guide for the four Prometheus alert rules that gate the PM Arb Signal Feed (spec [docs/superpowers/specs/2026-04-15-arb-signal-feed-design.md](../superpowers/specs/2026-04-15-arb-signal-feed-design.md) §11). Referenced by the `runbook_url` annotation on each rule in [monitoring/alert_rules.yml](../../monitoring/alert_rules.yml).

If you're paged: **look at the alert's `description` first** — it carries the triage ladder. This document is the backing reference.

## Shared context

All four alerts depend on metrics the trading engine emits on `/metrics`. Prometheus scrapes every 15s; alert rules evaluate every 15s. A fresh container takes ~45s to finish lifespan startup, so give a new deploy at least a minute before assuming an alert is real.

Key metrics:

| Metric | Source | Emitted by |
|---|---|---|
| `feed_arb_signals_published_total` | Publisher | `FeedPublisher._publish_signal` in [trading/feeds/publisher.py](../../trading/feeds/publisher.py) |
| `feed_arb_signals_dropped_total{reason}` | Publisher | same, labelled by drop reason |
| `feed_arb_pnl_rollup_last_tick_ts_seconds` | Attribution tick loop | `tick()`'s `finally:` block in [trading/feeds/pnl_attribution.py](../../trading/feeds/pnl_attribution.py) |
| `feed_arb_pnl_rollup_last_ts_seconds` | Attribution write | `_write_rollup` in same file |
| `feed_arb_pnl_rollup_writes_total` | Attribution write | same |
| `feed_arb_public_cache_{hits,misses}_total` | Public route | [trading/api/routes/feeds.py](../../trading/api/routes/feeds.py) |
| `http_request_duration_seconds_bucket{handler}` | FastAPI Instrumentator | `Instrumentator().instrument(...)` in [trading/api/app.py](../../trading/api/app.py) |

Dashboards: Grafana → folder "Feed Arb" → **Arb Feed — Public Endpoint SLO** ([dashboard JSON](../../monitoring/grafana/dashboards/arb-feed-slo.json)). Pull the relevant panel before diving into shell.

---

## D3 · `FeedArbAttributionStall`

**What it means:** `FeedArbPnLAttribution.tick()` hasn't completed in over 5 minutes. The `finally:` block at the top of `tick()` advances the `*_last_tick_ts_seconds` gauge on *every* exit path — including no-fill ticks and exception paths — so a stale value means the loop itself is stuck.

**What it doesn't mean:** quiet markets with no fills. The `*_last_ts_seconds` gauge (tied to actual rollup writes) will go stale during quiet periods by design, but D3 doesn't key off that gauge.

### Triage ladder

1. **Is the trading container up?**
   ```bash
   docker ps | grep trading
   ```
   If no, check `docker logs` for the reason and restart.

2. **Is the attribution task running?**
   ```bash
   docker logs agent-memory-unified-trading-1 --since=10m | grep feeds.pnl_attribution
   ```
   Expected: `tick()` shows activity every 60s (default `STA_FEED_ATTRIBUTION_INTERVAL_SECONDS`). If you see nothing, the task itself probably died on an unhandled exception that raised past the `finally:` block.

3. **Did the task get cancelled?**
   ```bash
   docker logs ... | grep "Background task 'feed_pnl_attribution'"
   ```
   If it shows a cancellation line without a restart, the task manager is wedged.

4. **Event-loop starvation?** Rare but possible if another task hogs CPU. Check container CPU usage. If pinned at 100%, the loop can stall enough for the gauge to fall stale.

### Common fixes

- **Restart trading container.** The background-task manager re-registers `feed_pnl_attribution` during lifespan startup; a clean restart is usually enough.
- **Check recent deploys.** If the last commit touched `pnl_attribution.py` and D3 fires right after, the new code probably raises pre-`finally`.

### Public-dashboard impact

While D3 is firing: `/api/v1/feeds/arb/public` continues serving the last cached rollup from Redis (10s TTL) until either the cache expires or a new rollup lands. Users see stale PnL. This is less bad than 500s or fabricated numbers (honest-tracker) but still a credibility issue — **remediate within the hour**.

---

## D4a · `FeedArbPublisherDroppedSignalsElevated`

**What it means:** signals are being dropped at the publisher for a reason *other* than `below_min_profit_bps` (which is normal cost-model churn). Fires at >0.1 drops/s over 5m on any other label.

### Reason breakdown

| label value | What it means |
|---|---|
| `store_error` | DB write to `feed_arb_signals` failed — check Postgres health |
| `missing_observation_id` | Upstream `arb.spread` event shape broke (schema drift in `cross_platform_arb`) |
| `missing_tickers` | Same — one of `kalshi_ticker` or `poly_ticker` is absent from the event payload |
| `below_min_profit_bps` | **Excluded from this alert** — normal churn |

### Triage ladder

1. ```bash
   docker logs agent-memory-unified-trading-1 --since=15m | grep feed_arb
   ```
   Look for `publisher_dropped` log events; each drop logs the observation_id and reason.

2. **Is the publisher still emitting at all?**
   ```promql
   rate(feed_arb_signals_published_total[5m])
   ```
   If zero, the D4b alert (`FeedArbPublisherZeroPublish`) should also be firing. Both firing together = total publisher failure. Only D4a = partial loss.

3. **Postgres health:**
   ```bash
   docker exec agent-memory-unified-postgres-1 pg_isready
   ```
   If `store_error` dominates, this is the likely root cause.

### Common fixes

- **Schema drift.** The most common post-incident cause: `cross_platform_arb` strategy started emitting events without one of the required fields. Recent commits to `trading/strategies/cross_platform_arb.py` are suspect.
- **DB permissions / connection pool exhaustion.** Check `asyncpg` connection count against pool size.

---

## D4b · `FeedArbPublisherZeroPublish`

**What it means:** `feed_arb_signals_published_total` hasn't advanced in 2 hours, but has published in the past. This is the **Risk #1 mitigation** from the plan — the silent-failure class that hit us in Phase A0. Ship this alert firing = emergency.

The `cross_platform_arb` cron runs every 30 minutes; 2h of zero publishes means ≥4 consecutive cron cycles produced nothing reachable to the publisher.

### Triage ladder

1. **Does the cron scan itself work?**
   ```bash
   curl -H "X-API-Key: $KEY" -X POST \
     http://localhost:8080/agents/cross_platform_arb/scan
   ```
   - Returns a populated array → adapter + cron are fine, publisher is the fault.
   - Returns `[]` → adapter/data layer is the fault (Kalshi API, Polymarket API, or the matcher).
   - 500s → check trading logs for a stack trace.

2. **Are `arb.spread` EventBus events firing?**
   ```bash
   docker exec agent-memory-unified-postgres-1 psql -U postgres -d agent_memory \
     -c "SELECT COUNT(*) FROM arb_spread_observations WHERE observed_at > NOW() - INTERVAL '30 minutes';"
   ```
   - Zero → scan produces nothing OR `SpreadStore.record` is silently failing.
   - Non-zero → `FeedPublisher` loop isn't subscribing to the topic, or the `CostModel.should_execute` gate is rejecting everything.

3. **Is the CostModel gate 100% rejecting?**
   ```promql
   rate(feed_arb_signals_dropped_total{reason="below_min_profit_bps"}[30m])
   ```
   If that rate is non-trivial while published_total is flat, the spreads are real but the min-profit bar is too high.

4. **Silent-exception swallowing.** The A0 incident had this class hit multiple times. Audit recent commits to `trading/feeds/publisher.py` for `except Exception: logger.warning(...non-fatal...)` patterns — upgrade those to `log_event("error", ...)` so D4 sees them.

### Common fixes

- **Adapter outage.** Kalshi or Polymarket API is down — check vendor status. Nothing to do but wait.
- **Rate limits.** Adapter is 429ing. Check the data-source rate-limit metrics.
- **Config placeholder.** `cross_platform_arb` was missing from `agents.paper.yaml` once; a regression here would reproduce. Double-check agents yaml.

---

## D6 · `FeedArbSubscriberChurn`

**What it means:** `/api/v1/feeds/arb/signals` saw 2xx traffic in the last 24h but zero 2xx in the last 10m. Fires post-G5 (paid launch) when paying subscribers stop polling.

Pre-launch this alert is silent because the 24h gate (`rate([24h]) > 0`) keeps it disarmed until the first paid customer starts polling.

### Triage ladder

1. **Is the route up?**
   ```bash
   curl -s -o /dev/null -w '%{http_code}' \
     http://localhost:8080/api/v1/feeds/arb/signals
   ```
   Expected: `401` (auth gate). If `5xx`, the route itself is failing — check trading logs and the `require_scope("read:feeds.arb")` dependency chain.

2. **Are API keys still valid?**
   ```sql
   SELECT name, status, last_used_at FROM agents
   WHERE 'read:feeds.arb' = ANY(scopes)
     AND last_used_at < NOW() - INTERVAL '10 minutes';
   ```
   If all feed subscribers flipped to revoked or expired, that explains the drop.

3. **Rate-limiter blanket 429s?**
   ```promql
   rate(http_requests_total{handler="/api/v1/feeds/arb/signals",status="429"}[10m])
   ```
   If non-zero, the rate limiter is probably blocking legitimate traffic. Check `trading/api/middleware/limiter.py` for tier config drift.

### Common fixes

- **Webhook / API-key rotation.** Proactively notify subscribers before rotating keys.
- **Rate-limit regression.** A recent change to `get_tier_limit` or the `feed_sub` tier defaults would do this.

---

## What's NOT in this runbook

- `cross_platform_arb` strategy-level debugging (adapter matching, spread-scoring) — out of scope; that's a feature-owner page not an ops page.
- LLM-cost budget exhaustion — handled by a separate alert + the `CostLedger` grace-period logic in [trading/llm/cost_ledger.py](../../trading/llm/cost_ledger.py).
- Redis outages — visible as cache-hit-ratio drops in D5, but the public route falls back to DB. Not a pager on its own.

## Maintenance

When adding a new alert: drop a matching section here, reference it via `annotations.runbook_url` in the rule, and add a link from the alert `description` to the section anchor. Keep this file co-located with the rules so drift surfaces on review.
