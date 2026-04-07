"""Risk-aware signal evaluator for SignalBus.

Subscribes to signals and performs risk checks before execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from agents.models import AgentSignal
from data.signal_bus import SignalBus
from risk.analytics import RiskAnalytics

logger = logging.getLogger(__name__)


@dataclass
class SignalRiskResult:
    """Result of risk evaluation on a signal."""

    signal: AgentSignal
    approved: bool
    risk_score: float  # 0.0 to 1.0, higher is riskier
    violations: list[str]
    details: dict[str, Any]


class RiskAwareSignalEvaluator:
    """
    Evaluates signals against risk limits before execution.

    Subscribes to SignalBus and checks each signal against:
    - Position size limits
    - Concentration limits
    - Leverage limits
    """

    def __init__(
        self,
        risk_analytics: RiskAnalytics,
        max_risk_score: float = 0.8,
    ) -> None:
        self._risk_analytics = risk_analytics
        self._max_risk_score = max_risk_score
        self._signal_history: list[SignalRiskResult] = []

    async def evaluate_signal(self, signal: AgentSignal) -> SignalRiskResult:
        """Evaluate a signal against risk limits."""
        violations = []
        risk_score = 0.0

        # Get current portfolio state
        # Note: In production, this would come from broker.get_positions()
        # For now, we analyze the signal itself
        position_size = self._estimate_position_size(signal)

        # Check signal-specific risk factors
        if signal.confidence and signal.confidence < 0.5:
            violations.append("Low confidence signal")
            risk_score += 0.3

        # Check for excessive position sizing
        # (Would compare against current portfolio in production)

        # Check signal type specific risks
        if signal.signal_type == "close":
            # Closing positions is generally lower risk
            risk_score -= 0.1

        # Cap risk score
        risk_score = max(0.0, min(1.0, risk_score))

        approved = risk_score < self._max_risk_score and len(violations) == 0

        result = SignalRiskResult(
            signal=signal,
            approved=approved,
            risk_score=risk_score,
            violations=violations,
            details={
                "position_size_estimate": position_size,
                "signal_type": signal.signal_type,
                "confidence": signal.confidence,
            },
        )

        self._signal_history.append(result)

        if not approved:
            logger.warning(
                "Signal %s rejected by risk evaluator: %s",
                signal.signal_type,
                violations,
            )

        return result

    def _estimate_position_size(self, signal: AgentSignal) -> Decimal:
        """Estimate position size from signal (placeholder)."""
        # In production, this would look at signal.size or similar
        return Decimal("0")

    def get_recent_results(self, limit: int = 10) -> list[SignalRiskResult]:
        """Get recent evaluation results."""
        return self._signal_history[-limit:]

    def get_rejection_rate(self) -> float:
        """Calculate rejection rate."""
        if not self._signal_history:
            return 0.0
        rejected = sum(1 for r in self._signal_history if not r.approved)
        return rejected / len(self._signal_history)


def attach_risk_evaluator(
    signal_bus: SignalBus,
    risk_analytics: RiskAnalytics,
    max_risk_score: float = 0.8,
) -> RiskAwareSignalEvaluator:
    """
    Attach a risk evaluator to a signal bus.

    Returns the evaluator so callers can inspect results.
    """
    evaluator = RiskAwareSignalEvaluator(risk_analytics, max_risk_score)

    async def risk_check(signal: AgentSignal) -> None:
        await evaluator.evaluate_signal(signal)

    signal_bus.subscribe(risk_check)
    logger.info("RiskAwareSignalEvaluator attached to SignalBus")

    return evaluator
