# PM Arb Signal Feed — SLO Dashboard (D5)

**Status:** Spec for a future Grafana/Prometheus dashboard. Not yet built — no observability stack is deployed in Railway. This doc is the contract so the next session picks up from a clear starting point.

**Spec reference:** [2026-04-15-arb-signal-feed-design.md §11](../../superpowers/specs/2026-04-15-arb-signal-feed-design.md)
**Plan reference:** D5 from the Phase D observability spine

---

## Why this is a doc, not code

Spec §11 lists SLIs with numeric targets. D3/D4/D6 are runtime *alerts* — those shipped as [feeds/health_monitor.py](../../../trading/feeds/health_monitor.py) driving the existing `CompositeNotifier` (Slack/Discord/WhatsApp). D5 is a *dashboard* — rendered by Grafana or equivalent, which we don't have deployed yet. Until then, the metrics live on `/metrics` (Prometheus scrape endpoint already exposed by the trading service) and this doc specifies the queries.

When the observability stack lands, someone can translate this file directly into a Grafana dashboard JSON.

---

## Panels

### 1. Publisher throughput

**SLI:** rate of `feed_arb_signals_published_total`.
**Target:** ≥ 1 publish per hour when the upstream `arb.spread` stream is emitting.
**Alert:** D4 (sustained zero publish over 2h window).

```promql
# Panel: publishes per hour (rate × 3600)
rate(feed_arb_signals_published_total[1h]) * 3600

# Panel: total lifetime publishes
feed_arb_signals_published_total
```

### 2. Publisher drop rate by reason

**SLI:** `feed_arb_signals_dropped_total` labeled by reason. Should be dominated by `below_min_profit_bps` (normal CostModel rejections). Anything else signals a pipeline bug.

```promql
# Panel: drops per hour by reason, stacked
sum by (reason) (rate(feed_arb_signals_dropped_total[1h]) * 3600)

# Panel: non-profit-gate drops (should be near zero)
sum (rate(feed_arb_signals_dropped_total{reason!="below_min_profit_bps"}[1h])) * 3600
```

### 3. Public endpoint latency

**SLI:** p50 / p95 / p99 response time on `/api/v1/feeds/arb/public`.
**Target:** p95 < 200ms (spec §11).
**Alert threshold:** p95 > 500ms for 10 min → warn (not yet wired; add when Grafana lands).

The trading service exposes the default `http_request_duration_seconds` histogram from `prometheus-fastapi-instrumentator` (see commit `47c5e14`). Filter by handler:

```promql
# Panel: p95 latency on the public route
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket{handler="/api/v1/feeds/arb/public"}[5m])
)

# Panel: p50 / p95 / p99 stacked
histogram_quantile(0.50, rate(http_request_duration_seconds_bucket{handler="/api/v1/feeds/arb/public"}[5m]))
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{handler="/api/v1/feeds/arb/public"}[5m]))
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{handler="/api/v1/feeds/arb/public"}[5m]))
```

### 4. Public cache hit ratio

**SLI:** Redis cache hit ratio on the public endpoint.
**Target:** > 98% at steady state (spec §A7 acceptance — 100 concurrent browsers × 10s polling → ≤6 DB reads/min).

```promql
# Panel: hit ratio (0.0–1.0)
rate(feed_arb_public_cache_hits_total[5m])
/
(rate(feed_arb_public_cache_hits_total[5m]) + rate(feed_arb_public_cache_misses_total[5m]))
```

### 5. Subscriber API error rate

**SLI:** 4xx + 5xx rate on `/api/v1/feeds/arb/signals`.
**Target:** < 1% overall (spec §11). 401/403 are expected (auth failures) — measure 5xx separately.

```promql
# Panel: 5xx rate (the alarming one)
sum(rate(http_requests_total{handler="/api/v1/feeds/arb/signals", status=~"5.."}[5m]))
/
sum(rate(http_requests_total{handler="/api/v1/feeds/arb/signals"}[5m]))

# Panel: 4xx rate (informational — scope rejections, bad since params)
sum(rate(http_requests_total{handler="/api/v1/feeds/arb/signals", status=~"4.."}[5m]))
/
sum(rate(http_requests_total{handler="/api/v1/feeds/arb/signals"}[5m]))
```

### 6. Attribution freshness

**SLI:** age of latest `feed_arb_pnl_rollup.rollup_ts`. Complements D3 — the alert fires at > 5 min; the dashboard shows the trend.

This metric isn't on `/metrics` today (it's a DB query, not a counter). Add a Prometheus gauge in a follow-up, or run the query as part of the Grafana dashboard's PostgreSQL data source:

```sql
-- Grafana "TimescaleDB / PostgreSQL" panel query
SELECT
  EXTRACT(EPOCH FROM (NOW() - MAX(rollup_ts))) AS seconds_since_last_rollup
FROM feed_arb_pnl_rollup;
```

### 7. Outcome distribution

**SLI:** breakdown of `feed_arb_signals.outcome` (`filled` / `missed` / `dead_book_skipped` / pending).
**Target:** no hard SLO; this is descriptive. Useful as a "health of the strategy" visual for design partners.

```sql
-- Grafana PostgreSQL query
SELECT
  COALESCE(outcome, 'pending') AS outcome,
  COUNT(*) AS n
FROM feed_arb_signals
WHERE ts > NOW() - INTERVAL '24 hours'
GROUP BY outcome;
```

### 8. Alert-firing history

**SLI:** rate of `feed.health.alert` log events (from `FeedHealthMonitor`).
**Target:** zero is ideal; sustained non-zero means the feed is degraded.

Pull from structured logs (whatever log aggregation we add — Loki, BetterStack, Datadog, etc.). Key:

```
logger=feeds.health_monitor AND event_type=feed.health.alert
```

Group by `data.alert` (d3_attribution_stall, d4_publisher_zero, ...) to see which SLI is failing.

---

## Next steps when the observability stack lands

1. Deploy Prometheus as a Railway service, scraping `https://trading-production-4cb1.up.railway.app/metrics` every 15s
2. Deploy Grafana; add the Prometheus data source + a PostgreSQL data source pointed at the agent-memory DB
3. Import the queries above as panels in a "PM Arb Signal Feed" dashboard
4. Wire a Prometheus AlertManager rule for "publisher 5xx rate > 1% for 5 min" (the runtime path for D3/D4/D6 should stay in `FeedHealthMonitor` since it can dispatch via the existing `CompositeNotifier` without needing Alertmanager; Prometheus rules are for SLO-style aggregate alerts that `FeedHealthMonitor` can't compute from table state alone).

---

## Why `FeedHealthMonitor` does D3/D4 and NOT D5

`FeedHealthMonitor` runs in-process against the Postgres DB. It can efficiently answer "when was the last rollup?" (D3) and "how many signals in the last N hours?" (D4) from two SQL queries. It cannot efficiently answer "what's the p95 latency of the public endpoint?" (D5) without aggregating per-request timing itself, which is exactly what Prometheus histograms already do. D5 belongs on the metrics-scrape path, not in the DB-query monitor.
