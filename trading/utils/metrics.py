"""Prometheus metrics for trading engine.

Provides custom metrics for:
- Signals processed (counter)
- Enrichments applied (counter)
- Vetos issued (counter)
- Provider latency (histogram)
- Signal confidence distribution (histogram)
- Active positions (gauge)
"""

from __future__ import annotations

from functools import wraps

from prometheus_client import Counter, Gauge, Histogram

# Signal metrics
SIGNALS_PROCESSED = Counter(
    "trading_signals_processed_total",
    "Total signals processed",
    ["source"],  # "bittensor", "agent", "manual"
)

SIGNALS_CONSENSUS = Counter(
    "trading_signals_consensus_total",
    "Signals that reached consensus",
)

SIGNALS_VETOED = Counter(
    "trading_signals_vetoed_total",
    "Signals vetoed by risk checks",
    ["reason"],  # "circuit_breaker", "volatility", "regime"
)

SIGNAL_CONFIDENCE = Histogram(
    "trading_signal_confidence",
    "Distribution of signal confidence scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# Enrichment metrics
ENRICHMENTS_APPLIED = Counter(
    "trading_enrichments_applied_total",
    "Total signal enrichments applied",
    ["provider"],  # "regime", "risk_audit", "sentiment", "anomaly"
)

# Provider latency
PROVIDER_LATENCY = Histogram(
    "trading_provider_latency_seconds",
    "Latency of intelligence providers",
    ["provider"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Trading metrics
ACTIVE_POSITIONS = Gauge(
    "trading_active_positions",
    "Current number of active positions",
)

ORDERS_PLACED = Counter(
    "trading_orders_placed_total",
    "Total orders placed",
    ["side"],  # "buy", "sell"
)

ORDERS_EXECUTED = Counter(
    "trading_orders_executed_total",
    "Total orders executed",
    ["side", "status"],  # "buy/filled", "sell/filled", etc.
)

# Risk metrics
RISK_CHECKS_PASSED = Counter(
    "trading_risk_checks_passed_total",
    "Risk checks passed",
)

RISK_CHECKS_FAILED = Counter(
    "trading_risk_checks_failed_total",
    "Risk checks failed",
    ["check_type"],  # "position_size", "drawdown", "exposure"
)

# Bittensor metrics
MINER_SIGNALS_RECEIVED = Counter(
    "bittensor_miner_signals_received_total",
    "Total miner signals received",
)

MINER_SIGNALS_VALID = Counter(
    "bittensor_miner_signals_valid_total",
    "Valid miner signals after validation",
)

# ── PM Arb Signal Feed (spec: 2026-04-15-arb-signal-feed-design.md) ─────────────
# Reserved names owed by Phase D1 (observability). Labels are deliberately
# minimal so cardinality stays bounded — the signal-id is opaque, so no
# per-signal label.

FEED_ARB_SIGNALS_PUBLISHED_TOTAL = Counter(
    "feed_arb_signals_published_total",
    "Arb signals written to feed_arb_signals (after CostModel gate)",
)

FEED_ARB_SIGNALS_DROPPED_TOTAL = Counter(
    "feed_arb_signals_dropped_total",
    "Arb signals dropped before write",
    # Keep the reason set small and stable. Any new reason gets added here
    # first so the D4 alert rule can key off specific values.
    ["reason"],  # "below_min_profit_bps", "missing_observation_id",
                 # "missing_tickers", "store_error"
)

FEED_ARB_PUBLIC_CACHE_HITS_TOTAL = Counter(
    "feed_arb_public_cache_hits_total",
    "Redis cache hits on /api/v1/feeds/arb/public",
)

FEED_ARB_PUBLIC_CACHE_MISSES_TOTAL = Counter(
    "feed_arb_public_cache_misses_total",
    "Redis cache misses on /api/v1/feeds/arb/public (served from DB)",
)

# D3 attribution SLIs (spec §11). Three metrics, two purposes:
#
#   *_last_tick_ts_seconds (gauge, updated every tick whether or not a
#    rollup is written) is the D3 alert source — it fires when the tick
#    loop itself stops. Rollup writes are gated by the honest-tracker
#    rule (no rollup on zero fills), so a quiet market correctly shows
#    last_ts flat while last_tick keeps advancing.
#
#   *_last_ts_seconds (gauge) + *_writes_total (counter) remain for
#    diagnostic panels — they answer "when did a rollup last land?" and
#    "how many have we written?" without pretending stale values mean
#    stall.
FEED_ARB_PNL_ROLLUP_LAST_TICK_TS_SECONDS = Gauge(
    "feed_arb_pnl_rollup_last_tick_ts_seconds",
    "Unix timestamp of the most recent FeedArbPnLAttribution.tick() "
    "completion. Updated on every tick, regardless of whether a rollup "
    "was written. D3 alert source: if this falls >300s behind, the "
    "attribution loop is genuinely stuck.",
)

FEED_ARB_PNL_ROLLUP_LAST_TS_SECONDS = Gauge(
    "feed_arb_pnl_rollup_last_ts_seconds",
    "Unix timestamp of the most recent feed_arb_pnl_rollup row actually "
    "written. Diagnostic — NOT alert-load-bearing. Stale values here "
    "during quiet markets are correct (honest-tracker rule).",
)

FEED_ARB_PNL_ROLLUP_WRITES_TOTAL = Counter(
    "feed_arb_pnl_rollup_writes_total",
    "Total feed_arb_pnl_rollup rows written by FeedArbPnLAttribution. "
    "Only increments when a tick has real fills — honest-tracker rule.",
)


def track_latency(provider: str):
    """Decorator to track provider latency."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time

            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.perf_counter() - start
                PROVIDER_LATENCY.labels(provider=provider).observe(duration)

        return wrapper

    return decorator


def track_enrichment(provider: str):
    """Decorator to track enrichment counts."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if result is not None:
                ENRICHMENTS_APPLIED.labels(provider=provider).inc()
            return result

        return wrapper

    return decorator
