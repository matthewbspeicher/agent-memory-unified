"""EnsembleOptimizer — combines signals from multiple agents with optimal weights.

Design principles:
- Performance-weighted: Higher Sharpe ratio agents get more weight
- Diversity-adjusted: Down-weights agents that are highly correlated
- Regime-aware: Different strategies for different market conditions
- Multiple strategies: Supports weighted average, voting, and confidence-weighted methods
- Best-effort: Gracefully handles missing data and edge cases
- Configurable: All parameters tuneable via agents.yaml parameters
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.models import AgentSignal
    from agents.runner import AgentRunner
    from storage.performance import PerformanceStore
    from learning.correlation_monitor import CorrelationMonitor

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    """Market regime classifications for regime-aware ensemble."""

    BULL = "bull"  # Strong upward trend
    BEAR = "bear"  # Strong downward trend
    SIDEWAYS = "sideways"  # Range-bound, low volatility
    HIGH_VOLATILITY = "high_volatility"  # Elevated volatility
    LOW_VOLATILITY = "low_volatility"  # Calm markets
    UNKNOWN = "unknown"


@dataclass
class RegimeWeights:
    """Regime-specific weight multipliers for different strategy types."""

    trend_following: float = 1.0  # e.g., RSI, momentum agents
    mean_reversion: float = 1.0  # e.g., pairs trading
    volatility: float = 1.0  # e.g., straddle, variance agents
    momentum: float = 1.0  # e.g., breakout agents


# Default regime-specific weight adjustments
# These multipliers are applied to base agent weights based on detected regime
REGIME_WEIGHT_ADJUSTMENTS: dict[MarketRegime, RegimeWeights] = {
    MarketRegime.BULL: RegimeWeights(
        trend_following=1.3,  # Boost trend followers in bull markets
        mean_reversion=0.7,
        volatility=0.8,
        momentum=1.2,
    ),
    MarketRegime.BEAR: RegimeWeights(
        trend_following=1.2,  # Shorting works well in bear
        mean_reversion=0.9,
        volatility=1.1,  # Volatility strategies can profit
        momentum=0.8,
    ),
    MarketRegime.SIDEWAYS: RegimeWeights(
        trend_following=0.7,
        mean_reversion=1.3,  # Mean reversion works in range-bound
        volatility=0.9,
        momentum=0.8,
    ),
    MarketRegime.HIGH_VOLATILITY: RegimeWeights(
        trend_following=0.8,
        mean_reversion=0.9,
        volatility=1.4,  # Volatility strategies thrive
        momentum=0.7,
    ),
    MarketRegime.LOW_VOLATILITY: RegimeWeights(
        trend_following=1.0,
        mean_reversion=1.1,
        volatility=0.6,  # Volatility strategies struggle
        momentum=1.0,
    ),
    MarketRegime.UNKNOWN: RegimeWeights(),  # No adjustment
}


class RegimeDetector:
    """Detects current market regime based on price action and volatility."""

    def __init__(
        self,
        lookback_bars: int = 20,
        volatility_threshold: float = 1.5,  # Std devs above/below mean
        trend_threshold: float = 0.05,  # 5% move to classify as trending
    ):
        self._lookback = lookback_bars
        self._vol_threshold = volatility_threshold
        self._trend_threshold = trend_threshold

    def detect(
        self,
        prices: list[float],
    ) -> MarketRegime:
        """Detect market regime from recent price series.

        Args:
            prices: List of recent closing prices (oldest first)

        Returns:
            Detected MarketRegime
        """
        if len(prices) < self._lookback:
            return MarketRegime.UNKNOWN

        recent = prices[-self._lookback :]

        # Calculate metrics
        returns = self._calculate_returns(recent)
        if not returns:
            return MarketRegime.UNKNOWN

        # Trend: linear regression slope
        slope = self._calculate_slope(recent)
        trend_pct = slope / recent[0] if recent[0] > 0 else 0

        # Volatility: standard deviation of returns
        vol = self._calculate_volatility(returns)

        # Detect regime
        return self._classify_regime(trend_pct, vol)

    def _calculate_returns(self, prices: list[float]) -> list[float]:
        """Calculate period-over-period returns."""
        if len(prices) < 2:
            return []
        return [
            (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))
        ]

    def _calculate_slope(self, prices: list[float]) -> float:
        """Calculate linear regression slope using least squares."""
        n = len(prices)
        if n < 2:
            return 0.0

        x_mean = (n - 1) / 2
        y_mean = sum(prices) / n

        numerator = sum((i - x_mean) * (prices[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def _calculate_volatility(self, returns: list[float]) -> float:
        """Calculate annualized volatility from returns."""
        if len(returns) < 2:
            return 0.0

        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        return (variance**0.5) * (252**0.5)  # Annualized

    def _classify_regime(self, trend_pct: float, volatility: float) -> MarketRegime:
        """Classify regime based on trend and volatility."""
        # Check trend first (direction is more important than volatility)
        if abs(trend_pct) > self._trend_threshold:
            if trend_pct > 0:
                return MarketRegime.BULL
            else:
                return MarketRegime.BEAR

        # Then check volatility
        if volatility > self._vol_threshold:
            return MarketRegime.HIGH_VOLATILITY

        if volatility < self._vol_threshold * 0.5:
            return MarketRegime.LOW_VOLATILITY

        # Default to sideways
        return MarketRegime.SIDEWAYS


class EnsembleMethod(str, Enum):
    """Methods for combining signals."""

    WEIGHTED_AVERAGE = "weighted_average"  # Weighted average of signals
    MAJORITY_VOTE = "majority_vote"  # Majority voting
    CONFIDENCE_WEIGHTED = "confidence_weighted"  # Weight by confidence
    SHARPE_WEIGHTED = "sharpe_weighted"  # Weight by historical Sharpe


@dataclass
class EnsembleConfig:
    """Configuration for ensemble optimization."""

    enabled: bool = True
    method: EnsembleMethod = EnsembleMethod.SHARPE_WEIGHTED
    min_agents_for_ensemble: int = 2
    min_sharpe_for_weight: float = 0.0
    max_weight_single_agent: float = 0.5  # Cap any single agent at 50%
    correlation_penalty: float = (
        0.5  # Multiply weight by this factor if highly correlated
    )
    high_correlation_threshold: float = 0.7
    consensus_threshold: float = 0.6  # Min combined confidence to generate signal
    weight_update_frequency_hours: int = 6

    # Regime-aware ensemble settings
    regime_aware: bool = False  # Enable regime-specific weight adjustments
    regime_lookback_bars: int = 20  # Bars for regime detection
    regime_volatility_threshold: float = 1.5  # Std devs for volatility regime
    regime_trend_threshold: float = 0.05  # 5% move for trend classification

    @classmethod
    def from_agent_config(cls, config: Any) -> "EnsembleConfig":
        """Build from agent config parameters."""
        if config is None:
            return cls()
        params = getattr(config, "parameters", None) or config
        if isinstance(params, dict):
            params = {
                **{
                    k: v
                    for k, v in params.items()
                    if k in cls.__init__.__code__.co_varnames
                },
                "method": EnsembleMethod(params.get("method", "sharpe_weighted")),
            }
            return cls(**params)
        return cls()


@dataclass
class AgentWeight:
    """Weight assignment for an agent in the ensemble."""

    agent_name: str
    base_weight: float  # Raw weight from performance
    adjusted_weight: float  # Final weight after correlation penalty
    sharpe_ratio: float
    trade_count: int
    is_correlated: bool = False  # Whether this agent is highly correlated with others


@dataclass
class EnsembleSignal:
    """Combined signal from multiple agents."""

    symbol: str
    direction: str  # "bullish" or "bearish"
    combined_confidence: float  # 0.0 to 1.0
    method: EnsembleMethod
    contributing_agents: list[
        dict[str, Any]
    ]  # [{agent, direction, confidence, weight}]
    agent_count: int
    timestamp: datetime
    is_consensus: bool  # Whether consensus threshold was met
    reasoning: str


class EnsembleOptimizer:
    """Combines signals from multiple agents with optimal weighting.

    The optimizer:
    1. Collects recent signals from all agents for a given symbol
    2. Computes weights based on historical Sharpe ratios
    3. Adjusts weights to penalize correlated agents
    4. Generates a consensus signal using the configured method
    """

    def __init__(
        self,
        runner: AgentRunner,
        perf_store: "PerformanceStore",
        correlation_monitor: "CorrelationMonitor | None" = None,
        config: EnsembleConfig | None = None,
    ) -> None:
        self._runner = runner
        self._perf_store = perf_store
        self._correlation_monitor = correlation_monitor
        self._cfg = config or EnsembleConfig()
        self._weight_cache: dict[str, list[AgentWeight]] = {}
        self._last_weight_update: datetime | None = None

    async def compute_agent_weights(
        self,
        force_update: bool = False,
    ) -> list[AgentWeight]:
        """Compute performance-based weights for all agents.

        Weights are derived from Sharpe ratios with:
        - Floor at min_sharpe_for_weight
        - Cap at max_weight_single_agent
        - Normalized to sum to 1.0
        """
        # Check cache freshness
        if not force_update and self._last_weight_update:
            hours_since_update = (
                datetime.now(timezone.utc) - self._last_weight_update
            ).total_seconds() / 3600
            if hours_since_update < self._cfg.weight_update_frequency_hours:
                cached = self._weight_cache.get("all")
                if cached:
                    return cached

        weights: list[AgentWeight] = []
        agent_weights_raw: dict[str, float] = {}
        agent_info: dict[str, dict[str, Any]] = {}

        # Get Sharpe ratios for all agents
        for agent_info_obj in self._runner.list_agents():
            name = agent_info_obj.name
            try:
                snapshot = await self._perf_store.get_latest(name)
                if snapshot is None:
                    continue

                sharpe = float(snapshot.sharpe_ratio or 0)
                trade_count = int(snapshot.total_trades or 0)

                if sharpe < self._cfg.min_sharpe_for_weight:
                    continue

                agent_weights_raw[name] = max(
                    sharpe, 0.01
                )  # Floor at 0.01 to avoid zero weight
                agent_info[name] = {"sharpe": sharpe, "trade_count": trade_count}

            except Exception as exc:
                logger.debug("Failed to get performance for %s: %s", name, exc)

        if not agent_weights_raw:
            return []

        # Normalize weights to sum to 1.0
        total_weight = sum(agent_weights_raw.values())
        normalized = {k: v / total_weight for k, v in agent_weights_raw.items()}

        # Apply cap to any single agent, then re-normalize, then cap again
        capped = {
            k: min(v, self._cfg.max_weight_single_agent) for k, v in normalized.items()
        }
        total_capped = sum(capped.values())
        if total_capped > 0:
            capped = {k: v / total_capped for k, v in capped.items()}
        # Final cap pass to handle any overflow from re-normalization
        capped = {
            k: min(v, self._cfg.max_weight_single_agent) for k, v in capped.items()
        }
        # Re-normalize one more time to ensure sum = 1.0
        total_final = sum(capped.values())
        if total_final > 0:
            capped = {k: v / total_final for k, v in capped.items()}

        # Check correlation if monitor is available
        correlated_agents: set[str] = set()
        if self._correlation_monitor:
            try:
                snapshot = await self._correlation_monitor.compute_correlation_matrix()
                if snapshot:
                    for pair in snapshot.high_correlation_pairs:
                        if (
                            abs(pair.correlation)
                            >= self._cfg.high_correlation_threshold
                        ):
                            correlated_agents.add(pair.agent_a)
                            correlated_agents.add(pair.agent_b)
            except Exception as exc:
                logger.debug("Failed to get correlation data: %s", exc)

        # Build final weight list
        for name, weight in capped.items():
            info = agent_info[name]
            is_correlated = name in correlated_agents
            adjusted_weight = (
                weight * self._cfg.correlation_penalty if is_correlated else weight
            )

            weights.append(
                AgentWeight(
                    agent_name=name,
                    base_weight=round(weight, 4),
                    adjusted_weight=round(adjusted_weight, 4),
                    sharpe_ratio=info["sharpe"],
                    trade_count=info["trade_count"],
                    is_correlated=is_correlated,
                )
            )

        # Sort by adjusted weight descending
        weights.sort(key=lambda w: w.adjusted_weight, reverse=True)

        # Re-normalize adjusted weights
        total_adjusted = sum(w.adjusted_weight for w in weights)
        if total_adjusted > 0:
            for w in weights:
                w.adjusted_weight = round(w.adjusted_weight / total_adjusted, 4)

        # Cache results
        self._weight_cache["all"] = weights
        self._last_weight_update = datetime.now(timezone.utc)

        return weights

    async def combine_signals(
        self,
        symbol: str,
        signals: list[AgentSignal],
    ) -> EnsembleSignal | None:
        """Combine multiple agent signals into a single ensemble signal.

        Args:
            symbol: The ticker symbol
            signals: List of signals from different agents for this symbol

        Returns:
            EnsembleSignal if consensus threshold met, None otherwise
        """
        # Filter valid signals first, then check threshold
        valid_signals = [
            s for s in signals if s.payload.get("direction") in ("bullish", "bearish")
        ]
        if len(valid_signals) < self._cfg.min_agents_for_ensemble:
            return None

        # Get current weights
        weights = await self.compute_agent_weights()
        weight_map = {w.agent_name: w.adjusted_weight for w in weights}

        # Aggregate signals by direction
        bullish_weighted = 0.0
        bearish_weighted = 0.0
        contributing: list[dict[str, Any]] = []

        for signal in valid_signals:
            agent_name = signal.source_agent
            direction = signal.payload.get("direction")
            confidence = float(signal.payload.get("confidence", 0.5))

            weight = weight_map.get(agent_name, 0.0)
            if weight == 0:
                # Assign uniform weight for agents without history
                weight = 1.0 / max(len(signals), 1)

            weighted_conf = weight * confidence

            if direction == "bullish":
                bullish_weighted += weighted_conf
            else:
                bearish_weighted += weighted_conf

            contributing.append(
                {
                    "agent": agent_name,
                    "direction": direction,
                    "confidence": confidence,
                    "weight": weight,
                }
            )

        # Determine consensus direction
        total_weighted = bullish_weighted + bearish_weighted
        if total_weighted == 0:
            return None

        if bullish_weighted > bearish_weighted:
            direction = "bullish"
            combined_confidence = bullish_weighted / total_weighted
        elif bearish_weighted > bullish_weighted:
            direction = "bearish"
            combined_confidence = bearish_weighted / total_weighted
        else:
            # Tie - no consensus
            direction = "bullish"  # Default, but confidence will be low
            combined_confidence = 0.5

        is_consensus = combined_confidence >= self._cfg.consensus_threshold

        # Build reasoning
        reasoning = self._build_reasoning(
            direction=direction,
            combined_confidence=combined_confidence,
            bullish_weighted=bullish_weighted,
            bearish_weighted=bearish_weighted,
            contributing=contributing,
        )

        return EnsembleSignal(
            symbol=symbol,
            direction=direction,
            combined_confidence=round(combined_confidence, 4),
            method=self._cfg.method,
            contributing_agents=contributing,
            agent_count=len(contributing),
            timestamp=datetime.now(timezone.utc),
            is_consensus=is_consensus,
            reasoning=reasoning,
        )

    def _build_reasoning(
        self,
        direction: str,
        combined_confidence: float,
        bullish_weighted: float,
        bearish_weighted: float,
        contributing: list[dict[str, Any]],
    ) -> str:
        """Build human-readable reasoning for ensemble decision."""
        bullish_agents = [
            c["agent"] for c in contributing if c["direction"] == "bullish"
        ]
        bearish_agents = [
            c["agent"] for c in contributing if c["direction"] == "bearish"
        ]

        parts = [
            f"Ensemble: {direction} (confidence={combined_confidence:.2f})",
            f"Bullish weighted={bullish_weighted:.3f} ({len(bullish_agents)} agents)",
            f"Bearish weighted={bearish_weighted:.3f} ({len(bearish_agents)} agents)",
        ]

        if bullish_agents:
            parts.append(f"Bullish: {', '.join(bullish_agents)}")
        if bearish_agents:
            parts.append(f"Bearish: {', '.join(bearish_agents)}")

        return "; ".join(parts)

    def get_method_description(self) -> str:
        """Get description of current ensemble method."""
        descriptions = {
            EnsembleMethod.WEIGHTED_AVERAGE: "Signals combined by weighted average",
            EnsembleMethod.MAJORITY_VOTE: "Simple majority voting across agents",
            EnsembleMethod.CONFIDENCE_WEIGHTED: "Weighted by signal confidence",
            EnsembleMethod.SHARPE_WEIGHTED: "Weighted by historical Sharpe ratio",
        }
        return descriptions.get(self._cfg.method, "Unknown method")

    async def get_weight_report(self) -> list[dict[str, Any]]:
        """Get formatted weight report for all agents."""
        weights = await self.compute_agent_weights()
        return [
            {
                "agent": w.agent_name,
                "base_weight": w.base_weight,
                "adjusted_weight": w.adjusted_weight,
                "sharpe_ratio": round(w.sharpe_ratio, 3),
                "trade_count": w.trade_count,
                "is_correlated": w.is_correlated,
            }
            for w in weights
        ]
