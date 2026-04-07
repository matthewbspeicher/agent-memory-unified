# ADR-003: RiskAnalytics Module

**Status**: accepted

**Date**: 2026-04-07
**Deciders**: Development Team

---

## Context

The trading engine lacked real-time risk calculations for portfolio positions. We needed:
- Value at Risk (VaR) calculation for risk monitoring
- Drawdown tracking (current and max)
- Position-level and portfolio exposure metrics
- Leverage and margin utilization monitoring
- Configurable risk limits with violation detection

## Decision

Implement a RiskAnalytics module with three components:

### 1. RiskAnalytics (`trading/risk/analytics.py`)
- VaR 95%, VaR 99%, CVaR (Conditional VaR / Expected Shortfall)
- Drawdown tracking with running peak calculation
- Portfolio risk aggregation from positions
- Risk limit checking with violation reporting

### 2. RiskProviderCircuitBreaker (`trading/risk/circuit_breaker.py`)
- Three-state circuit breaker (Closed → Open → Half-Open)
- Per-provider failure tracking
- Automatic recovery testing in half-open state
- Manager for multiple providers

### 3. RiskAwareSignalEvaluator (`trading/risk/signal_evaluator.py`)
- Subscribes to SignalBus
- Evaluates signals against risk limits before execution
- Risk scoring (0-1) with rejection capability

## Consequences

### Positive
- Real-time portfolio risk monitoring via `/api/risk/analytics`
- Resilience against risk provider failures
- Pre-trade risk checks via SignalBus integration
- 36 unit tests covering all components

### Negative
- Additional dependency on NumPy for VaR calculations
- Risk evaluator adds latency to signal processing

### Neutral
- Module is optional - requires `risk_analytics` in app state
- Circuit breakers disabled by default (5 failures threshold, 60s timeout)
- Risk evaluator max_risk_score default: 0.8

---

## Alternatives Considered

| Alternative | Pros | Cons |
|-------------|------|------|
| Use existing RiskEngine | Already integrated | Only checks orders, not portfolio |
| Third-party risk library | Production-ready | Additional dependency |
| Manual risk calculations | Full control | Error-prone, not scalable |

---

## Notes

- Risk limits configurable via `RiskLimit` dataclass
- VaR uses historical simulation method
- Drawdown calculates running peak correctly (not just final peak)
- API endpoint requires `X-API-Key` authentication
- Circuit breaker states: CLOSED (normal), OPEN (failing), HALF_OPEN (testing recovery)