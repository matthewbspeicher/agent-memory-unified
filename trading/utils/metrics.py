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
