# Risk Analytics Module

Real-time risk monitoring for the trading engine.

## Overview

The RiskAnalytics module provides three layers of risk management:

1. **RiskAnalytics** — Real-time portfolio risk calculations
2. **RiskProviderCircuitBreaker** — Resilience for external risk data providers
3. **RiskAwareSignalEvaluator** — Pre-trade risk checks via SignalBus

## Quick Start

```python
from trading.risk import RiskAnalytics, RiskLimit, PortfolioRisk

# Create with custom limits
limits = RiskLimit(
    max_var_95_pct=0.02,      # 2% of portfolio
    max_drawdown_pct=0.10,    # 10%
    max_leverage=2.0,         # 2x
)
analytics = RiskAnalytics(limits=limits)

# Calculate portfolio risk
positions = [
    {"symbol": "AAPL", "quantity": 100, "avg_price": 150.0}
]
prices = {"AAPL": Decimal("160.0")}
risk = analytics.calculate_portfolio_risk(positions, prices)

# Check for violations
violations = analytics.check_limits(risk)
```

## API Endpoint

```
GET /api/risk/analytics
Headers: X-API-Key: <your-key>
```

Returns:
```json
{
  "timestamp": "2026-04-07T12:00:00+00:00",
  "positions": { "total": 5, "long": 3, "short": 2 },
  "notional": { "long": "50000", "short": "30000", "net": "20000", "gross": "80000" },
  "var": { "95": "0.015", "99": "0.025", "cvar": "0.030" },
  "drawdown": { "current": "0.05", "max": "0.12", "peak_equity": "100000", "current_equity": "95000" },
  "leverage": { "current": "1.5", "max": "2.0" },
  "violations": []
}
```

## Circuit Breaker

```python
from trading.risk import RiskProviderCircuitBreakerManager

# Get or create breaker for a provider
manager = RiskProviderCircuitBreakerManager()
cb = manager.get_or_create("pricing_api", config=CircuitBreakerConfig(
    failure_threshold=5,
    timeout_seconds=60.0
))

# Use with async function
result = await cb.call(my_risk_function)
```

## SignalBus Integration

```python
from trading.risk import attach_risk_evaluator
from data.signal_bus import SignalBus

signal_bus = SignalBus()
evaluator = attach_risk_evaluator(signal_bus, risk_analytics)

# All signals are now checked before processing
# Inspect rejections:
rejection_rate = evaluator.get_rejection_rate()
```

## Risk Limits (Defaults)

| Limit | Default | Description |
|-------|---------|-------------|
| `max_var_95_pct` | 2% | 95% VaR as % of equity |
| `max_var_99_pct` | 4% | 99% VaR as % of equity |
| `max_drawdown_pct` | 10% | Max drawdown from peak |
| `max_leverage` | 2.0x | Gross notional / equity |
| `max_margin_utilization` | 80% | Margin used / available |

## Files

- `trading/risk/analytics.py` — Core risk calculations
- `trading/risk/circuit_breaker.py` — Provider resilience
- `trading/risk/signal_evaluator.py` — Signal evaluation
- `trading/risk/__init__.py` — Module exports
- `tests/unit/test_risk_analytics.py` — 25 tests
- `tests/unit/test_risk_circuit_breaker.py` — 11 tests