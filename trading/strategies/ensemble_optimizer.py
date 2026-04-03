# strategies/ensemble_optimizer.py
from __future__ import annotations
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from agents.base import StructuredAgent
from agents.models import Opportunity
from broker.models import Symbol
from data.bus import DataBus

logger = logging.getLogger(__name__)


@dataclass
class AgentPerformance:
    """Performance metrics for an agent."""

    agent_name: str
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    sharpe_ratio: float
    sample_count: int
    last_updated: datetime


@dataclass
class EnsembleWeights:
    """Optimized weights for ensemble of agents."""

    weights: dict[str, float]  # agent_name -> weight
    total_weight: float
    expected_return: float
    sharpe_ratio: float
    optimization_method: str
    timestamp: datetime


class EnsembleOptimizer(StructuredAgent):
    """Learns optimal weights for combining signals from multiple agents.

    Uses recent performance data to compute optimal allocation weights,
    producing higher-confidence combined signals.

    Parameters:
        lookback_days: Days of performance data to use. Default 7.
        min_trades_per_agent: Minimum trades to include agent. Default 20.
        rebalance_interval_hours: How often to recalculate weights. Default 4.
        optimization_method: "kelly", "equal_weight", or "sharpe". Default "kelly".
        target_agents: List of agents to include (empty = all). Default [].
        min_weight: Minimum weight for any agent. Default 0.05.
        max_weight: Maximum weight for any agent. Default 0.4.
    """

    _last_rebalance: datetime | None = None
    _cached_weights: EnsembleWeights | None = None
    _performance_cache: dict[str, AgentPerformance] = {}

    @property
    def description(self) -> str:
        method = self.parameters.get("optimization_method", "kelly")
        return f"Ensemble optimizer (method={method})"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        """Optimize ensemble weights and generate combined signals."""
        params = self.parameters
        lookback_days = params.get("lookback_days", 7)
        min_trades = params.get("min_trades_per_agent", 20)
        rebalance_hours = params.get("rebalance_interval_hours", 4)
        method = params.get("optimization_method", "kelly")
        target_agents = params.get("target_agents", [])
        min_weight = params.get("min_weight", 0.05)
        max_weight = params.get("max_weight", 0.4)

        now = datetime.now(timezone.utc)

        # Check if we need to rebalance
        if self._should_rebalance(now, rebalance_hours):
            await self._rebalance_weights(
                data,
                lookback_days,
                min_trades,
                method,
                target_agents,
                min_weight,
                max_weight,
                now,
            )

        # If we have cached weights, generate ensemble signals
        if self._cached_weights is None:
            return []

        return await self._generate_ensemble_signals(data, now)

    def _should_rebalance(self, now: datetime, rebalance_hours: int) -> bool:
        """Check if it's time to rebalance weights."""
        if self._last_rebalance is None:
            return True

        elapsed = (now - self._last_rebalance).total_seconds() / 3600
        return elapsed >= rebalance_hours

    async def _rebalance_weights(
        self,
        data: DataBus,
        lookback_days: int,
        min_trades: int,
        method: str,
        target_agents: list[str],
        min_weight: float,
        max_weight: float,
        now: datetime,
    ) -> None:
        """Recalculate optimal weights based on recent performance."""
        # Fetch performance data
        performance = await self._fetch_agent_performance(data, lookback_days)

        # Filter to target agents if specified
        if target_agents:
            performance = {k: v for k, v in performance.items() if k in target_agents}

        # Filter by minimum trades
        performance = {
            k: v for k, v in performance.items() if v.sample_count >= min_trades
        }

        if len(performance) < 2:
            logger.debug(
                "Ensemble optimizer: not enough agents with sufficient data "
                "(have %d, need >= 2)",
                len(performance),
            )
            return

        # Calculate weights based on method
        if method == "kelly":
            weights = self._kelly_weights(performance, min_weight, max_weight)
        elif method == "sharpe":
            weights = self._sharpe_weights(performance, min_weight, max_weight)
        else:  # equal_weight
            weights = self._equal_weights(performance, min_weight, max_weight)

        # Calculate ensemble metrics
        total_weight = sum(weights.values())
        expected_return = self._calculate_expected_return(performance, weights)
        sharpe = self._calculate_ensemble_sharpe(performance, weights)

        self._cached_weights = EnsembleWeights(
            weights=weights,
            total_weight=total_weight,
            expected_return=expected_return,
            sharpe_ratio=sharpe,
            optimization_method=method,
            timestamp=now,
        )
        self._last_rebalance = now
        self._performance_cache = performance

        logger.info(
            "Ensemble weights rebalanced: %s (method=%s, return=%.4f, sharpe=%.2f)",
            weights,
            method,
            expected_return,
            sharpe,
        )

    async def _fetch_agent_performance(
        self,
        data: DataBus,
        lookback_days: int,
    ) -> dict[str, AgentPerformance]:
        """Fetch performance metrics for all agents.

        Note: In a real implementation, this would query TradeStore/PerformanceStore.
        For now, returns empty dict - this is a framework that can be wired to actual data.
        """
        # TODO: Wire to actual performance store
        # This would query: trade_store.get_agent_performance(agent_name, lookback_days)
        # For now, return empty - the optimizer framework is in place
        return {}

    def _kelly_weights(
        self,
        performance: dict[str, AgentPerformance],
        min_weight: float,
        max_weight: float,
    ) -> dict[str, float]:
        """Calculate Kelly Criterion weights."""
        weights: dict[str, float] = {}

        for name, perf in performance.items():
            if perf.win_rate <= 0 or perf.win_rate >= 1:
                # Edge case: use equal weight
                weights[name] = 1.0 / len(performance)
                continue

            # Kelly fraction: f = (p * b - q) / b
            # where p = win_rate, q = 1 - p, b = avg_win / abs(avg_loss)
            if perf.avg_loss == 0:
                weights[name] = 1.0 / len(performance)
                continue

            b = perf.avg_win / abs(perf.avg_loss)
            p = perf.win_rate
            q = 1 - p

            kelly = (p * b - q) / b
            # Apply half-Kelly for safety
            kelly = max(0, kelly * 0.5)
            weights[name] = kelly

        # Apply weight bounds
        weights = self._apply_bounds(weights, min_weight, max_weight)

        # Normalize to sum to 1
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def _sharpe_weights(
        self,
        performance: dict[str, AgentPerformance],
        min_weight: float,
        max_weight: float,
    ) -> dict[str, float]:
        """Calculate weights proportional to Sharpe ratio."""
        weights: dict[str, float] = {}

        total_sharpe = sum(max(0, p.sharpe_ratio) for p in performance.values())

        if total_sharpe == 0:
            return self._equal_weights(performance, min_weight, max_weight)

        for name, perf in performance.items():
            weights[name] = max(0, perf.sharpe_ratio) / total_sharpe

        # Apply weight bounds
        weights = self._apply_bounds(weights, min_weight, max_weight)

        # Normalize
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def _equal_weights(
        self,
        performance: dict[str, AgentPerformance],
        min_weight: float,
        max_weight: float,
    ) -> dict[str, float]:
        """Equal weights for all agents."""
        n = len(performance)
        base_weight = 1.0 / n

        return {
            name: max(min_weight, min(max_weight, base_weight)) for name in performance
        }

    def _apply_bounds(
        self,
        weights: dict[str, float],
        min_weight: float,
        max_weight: float,
    ) -> dict[str, float]:
        """Apply min/max bounds to weights."""
        return {k: max(min_weight, min(max_weight, v)) for k, v in weights.items()}

    def _calculate_expected_return(
        self,
        performance: dict[str, AgentPerformance],
        weights: dict[str, float],
    ) -> float:
        """Calculate weighted expected return."""
        expected = 0.0
        for name, weight in weights.items():
            perf = performance.get(name)
            if perf:
                # Approximate: win_rate * avg_win - (1 - win_rate) * abs(avg_loss)
                expectancy = perf.win_rate * perf.avg_win - (1 - perf.win_rate) * abs(
                    perf.avg_loss
                )
                expected += weight * expectancy
        return expected

    def _calculate_ensemble_sharpe(
        self,
        performance: dict[str, AgentPerformance],
        weights: dict[str, float],
    ) -> float:
        """Calculate weighted Sharpe ratio."""
        weighted_sharpe = 0.0
        total_weight = sum(weights.values())

        if total_weight == 0:
            return 0.0

        for name, weight in weights.items():
            perf = performance.get(name)
            if perf:
                weighted_sharpe += (weight / total_weight) * perf.sharpe_ratio

        return weighted_sharpe

    async def _generate_ensemble_signals(
        self,
        data: DataBus,
        now: datetime,
    ) -> list[Opportunity]:
        """Generate ensemble signals based on current weights.

        This looks at recent opportunities from each agent and combines them
        using the optimized weights.
        """
        # TODO: In a real implementation, this would:
        # 1. Fetch recent opportunities from each agent
        # 2. Weight their signals by the optimized weights
        # 3. Generate a combined opportunity if consensus is reached

        # For now, emit a status opportunity with current weights
        if self._cached_weights is None:
            return []

        w = self._cached_weights
        symbol = Symbol(ticker="ENSEMBLE", asset_type=None)

        opp = Opportunity(
            id=str(uuid.uuid4()),
            agent_name=self.name,
            symbol=symbol,
            signal="hold",  # Status signal
            confidence=0.5,  # Neutral confidence
            reasoning=(
                f"Ensemble weights updated. "
                f"Agents: {len(w.weights)}. "
                f"Expected return: {w.expected_return:.4f}. "
                f"Sharpe: {w.sharpe_ratio:.2f}."
            ),
            data={
                "weights": w.weights,
                "expected_return": w.expected_return,
                "sharpe_ratio": w.sharpe_ratio,
                "optimization_method": w.optimization_method,
                "timestamp": w.timestamp.isoformat(),
                "status_type": "weight_update",
            },
            timestamp=now,
        )

        return [opp]

    @classmethod
    def get_current_weights(cls) -> EnsembleWeights | None:
        """Get current optimized weights (for external access)."""
        return cls._cached_weights

    @classmethod
    def get_agent_performance_summary(cls) -> dict[str, dict[str, float]]:
        """Get summary of cached performance data."""
        return {
            name: {
                "win_rate": perf.win_rate,
                "avg_win": perf.avg_win,
                "avg_loss": perf.avg_loss,
                "sharpe_ratio": perf.sharpe_ratio,
                "sample_count": perf.sample_count,
            }
            for name, perf in cls._performance_cache.items()
        }

    @classmethod
    def update_performance(
        cls,
        agent_name: str,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        profit_factor: float,
        sharpe_ratio: float,
        sample_count: int,
    ) -> None:
        """Update performance data for an agent (called externally)."""
        cls._performance_cache[agent_name] = AgentPerformance(
            agent_name=agent_name,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            sample_count=sample_count,
            last_updated=datetime.now(timezone.utc),
        )
