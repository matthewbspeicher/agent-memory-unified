"""Risk management module for trading engine.

Exports:
- RiskAnalytics: Real-time risk calculations (VaR, drawdown, exposure)
- RiskEngine: Position and order risk checks
- RiskRule: Configurable risk rules
- RiskLimit: Configurable risk limits
- RiskViolation: Risk limit breach notifications
- PositionRisk: Per-position risk metrics
- PortfolioRisk: Aggregated portfolio risk metrics
- RiskMetric: Enum of tracked risk metrics
- RiskProviderCircuitBreaker: Circuit breaker for risk providers
- RiskProviderCircuitBreakerManager: Manager for multiple providers
- RiskAwareSignalEvaluator: Risk evaluation for signals
- attach_risk_evaluator: Attach evaluator to SignalBus
- CircuitState: Circuit breaker states
- CircuitBreakerConfig: Circuit breaker configuration
- CircuitBreakerOpenError: Exception for open circuit
"""

from trading.risk.analytics import (
    PortfolioRisk,
    PositionRisk,
    RiskAnalytics,
    RiskLimit,
    RiskMetric,
    RiskViolation,
)
from trading.risk.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    RiskProviderCircuitBreaker,
    RiskProviderCircuitBreakerManager,
)
from trading.risk.signal_evaluator import (
    RiskAwareSignalEvaluator,
    SignalRiskResult,
    attach_risk_evaluator,
)

__all__ = [
    # Analytics
    "RiskAnalytics",
    "PortfolioRisk",
    "PositionRisk",
    "RiskLimit",
    "RiskMetric",
    "RiskViolation",
    # Circuit breaker
    "RiskProviderCircuitBreaker",
    "RiskProviderCircuitBreakerManager",
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    # Signal evaluator
    "RiskAwareSignalEvaluator",
    "SignalRiskResult",
    "attach_risk_evaluator",
]

# Also expose submodules for direct import
__all__ += [
    "analytics",
    "engine",
    "rules",
    "circuit_breaker",
    "signal_evaluator",
]
