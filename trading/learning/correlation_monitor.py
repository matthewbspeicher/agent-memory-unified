"""CorrelationMonitor — tracks rolling P&L correlations between trading agents.

Design principles:
- Rolling window: Uses configurable lookback (default 30 days) for correlation calculation
- Threshold-based alerts: Flags pairs exceeding correlation threshold (default 0.7)
- Diversification score: Computes portfolio-level diversification from correlation matrix
- Best-effort: Fails gracefully on missing data, logs warnings
- Non-blocking: Called via asyncio.create_task() from learning scheduler
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from storage.performance import PerformanceStore
    from storage.correlation import CorrelationStore

logger = logging.getLogger(__name__)


class CorrelationAlertLevel(str, Enum):
    """Alert levels for correlation warnings."""

    NORMAL = "normal"  # All correlations below threshold
    WARNING = "warning"  # 1-2 pairs above threshold
    CRITICAL = "critical"  # 3+ pairs above threshold or portfolio score too low


@dataclass
class CorrelationConfig:
    """Configuration for correlation monitoring."""

    enabled: bool = True
    lookback_days: int = 30
    min_trades_for_agent: int = 10
    high_correlation_threshold: float = 0.7
    critical_portfolio_score: float = 0.3
    alert_cooldown_hours: int = 6
    top_n_pairs_to_report: int = 5

    @classmethod
    def from_learning_config(cls, cfg: Any) -> "CorrelationConfig":
        """Build from learning.yaml correlation sub-section."""
        if cfg is None:
            return cls()
        if isinstance(cfg, dict):
            return cls(
                **{
                    k: v
                    for k, v in cfg.items()
                    if k in cls.__init__.__code__.co_varnames
                }
            )
        return cls(
            enabled=getattr(cfg, "enabled", True),
            lookback_days=getattr(cfg, "lookback_days", 30),
            min_trades_for_agent=getattr(cfg, "min_trades_for_agent", 10),
            high_correlation_threshold=getattr(cfg, "high_correlation_threshold", 0.7),
            critical_portfolio_score=getattr(cfg, "critical_portfolio_score", 0.3),
            alert_cooldown_hours=getattr(cfg, "alert_cooldown_hours", 6),
            top_n_pairs_to_report=getattr(cfg, "top_n_pairs_to_report", 5),
        )


@dataclass
class CorrelationPair:
    """Correlation between two agents."""

    agent_a: str
    agent_b: str
    correlation: float
    sample_size: int
    lookback_days: int


@dataclass
class CorrelationSnapshot:
    """Full correlation snapshot for all agent pairs."""

    timestamp: datetime
    alert_level: CorrelationAlertLevel
    portfolio_diversification_score: (
        float  # 0.0 (all correlated) to 1.0 (fully diversified)
    )
    high_correlation_pairs: list[CorrelationPair]
    agent_count: int
    analyzed_pairs: int
    skipped_pairs: int  # pairs with insufficient data


def compute_pearson_correlation(x: list[float], y: list[float]) -> float | None:
    """Compute Pearson correlation coefficient between two series.

    Returns None if:
    - Series have different lengths
    - Series have fewer than 3 data points
    - Either series has zero variance
    """
    n = len(x)
    if n != len(y) or n < 3:
        return None

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    # Compute numerator and denominators
    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    denom_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    denom_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

    if denom_x == 0 or denom_y == 0:
        return None

    return numerator / (denom_x * denom_y)


def compute_diversification_score(correlations: list[float]) -> float:
    """Compute portfolio diversification score from pairwise correlations.

    Score ranges from 0.0 (all agents perfectly correlated) to 1.0 (all uncorrelated/negatively correlated).

    Formula: 1 - avg(|correlation|) for all pairs with valid correlations.
    """
    if not correlations:
        return 1.0  # No correlations means maximum diversification

    abs_correlations = [abs(c) for c in correlations]
    avg_abs_corr = sum(abs_correlations) / len(abs_correlations)
    return 1.0 - avg_abs_corr


class CorrelationMonitor:
    """Monitors rolling P&L correlations between trading agents.

    Uses daily P&L snapshots from PerformanceStore to compute pairwise correlations.
    Identifies concentration risk when multiple agents move in lockstep.
    """

    def __init__(
        self,
        perf_store: "PerformanceStore",
        correlation_store: "CorrelationStore",
        config: CorrelationConfig | None = None,
    ) -> None:
        self._perf_store = perf_store
        self._correlation_store = correlation_store
        self._cfg = config or CorrelationConfig()
        self._last_alert_time: datetime | None = None

    async def compute_correlation_matrix(
        self,
        agent_names: list[str] | None = None,
    ) -> CorrelationSnapshot:
        """Compute full correlation matrix for all agents.

        Args:
            agent_names: Specific agents to analyze. If None, uses all active agents.

        Returns:
            CorrelationSnapshot with full matrix and alerts.
        """
        if not self._cfg.enabled:
            return CorrelationSnapshot(
                timestamp=datetime.now(timezone.utc),
                alert_level=CorrelationAlertLevel.NORMAL,
                portfolio_diversification_score=1.0,
                high_correlation_pairs=[],
                agent_count=0,
                analyzed_pairs=0,
                skipped_pairs=0,
            )

        # Get agent P&L time series
        agent_pnl_series: dict[str, list[float]] = {}
        cutoff_date = datetime.now(timezone.utc) - timedelta(
            days=self._cfg.lookback_days
        )

        # Fetch P&L data for each agent
        agents_to_analyze = agent_names or []
        if not agents_to_analyze:
            # If no specific agents provided, try to get from PerformanceStore
            try:
                snapshots = await self._perf_store.get_all_latest()
                if snapshots:
                    agents_to_analyze = [s.agent_name for s in snapshots]
            except Exception as exc:
                logger.warning(
                    "Failed to get agent list from PerformanceStore: %s", exc
                )
                return self._empty_snapshot()

        for agent_name in agents_to_analyze:
            try:
                daily_pnls = await self._perf_store.get_daily_pnl_series(
                    agent_name=agent_name,
                    start_date=cutoff_date.isoformat(),
                )
                if daily_pnls and len(daily_pnls) >= self._cfg.min_trades_for_agent:
                    agent_pnl_series[agent_name] = [float(p) for p in daily_pnls]
            except Exception as exc:
                logger.debug("Failed to get P&L series for %s: %s", agent_name, exc)

        if len(agent_pnl_series) < 2:
            return CorrelationSnapshot(
                timestamp=datetime.now(timezone.utc),
                alert_level=CorrelationAlertLevel.NORMAL,
                portfolio_diversification_score=1.0,
                high_correlation_pairs=[],
                agent_count=len(agent_pnl_series),
                analyzed_pairs=0,
                skipped_pairs=0,
            )

        # Compute pairwise correlations
        agent_names_list = sorted(agent_pnl_series.keys())
        all_correlations: list[float] = []
        high_corr_pairs: list[CorrelationPair] = []
        analyzed_pairs = 0
        skipped_pairs = 0

        for i in range(len(agent_names_list)):
            for j in range(i + 1, len(agent_names_list)):
                agent_a = agent_names_list[i]
                agent_b = agent_names_list[j]
                series_a = agent_pnl_series[agent_a]
                series_b = agent_pnl_series[agent_b]

                # Align series by taking minimum length
                min_len = min(len(series_a), len(series_b))
                if min_len < 3:
                    skipped_pairs += 1
                    continue

                corr = compute_pearson_correlation(
                    series_a[:min_len],
                    series_b[:min_len],
                )

                if corr is None:
                    skipped_pairs += 1
                    continue

                analyzed_pairs += 1
                all_correlations.append(corr)

                # Check if this pair exceeds threshold
                if abs(corr) >= self._cfg.high_correlation_threshold:
                    high_corr_pairs.append(
                        CorrelationPair(
                            agent_a=agent_a,
                            agent_b=agent_b,
                            correlation=round(corr, 4),
                            sample_size=min_len,
                            lookback_days=self._cfg.lookback_days,
                        )
                    )

        # Sort high correlation pairs by absolute value (highest first)
        high_corr_pairs.sort(key=lambda p: abs(p.correlation), reverse=True)

        # Compute portfolio diversification score
        portfolio_score = compute_diversification_score(all_correlations)

        # Determine alert level
        alert_level = self._determine_alert_level(len(high_corr_pairs), portfolio_score)

        snapshot = CorrelationSnapshot(
            timestamp=datetime.now(timezone.utc),
            alert_level=alert_level,
            portfolio_diversification_score=round(portfolio_score, 4),
            high_correlation_pairs=high_corr_pairs[: self._cfg.top_n_pairs_to_report],
            agent_count=len(agent_pnl_series),
            analyzed_pairs=analyzed_pairs,
            skipped_pairs=skipped_pairs,
        )

        # Persist snapshot
        try:
            await self._correlation_store.save_snapshot(snapshot)
        except Exception as exc:
            logger.warning("Failed to persist correlation snapshot: %s", exc)

        # Log alerts
        if alert_level != CorrelationAlertLevel.NORMAL:
            logger.warning(
                "CorrelationMonitor: %s - %d high-correlation pairs, portfolio score=%.2f",
                alert_level.value,
                len(high_corr_pairs),
                portfolio_score,
            )
            for pair in high_corr_pairs[:3]:
                logger.warning(
                    "  High correlation: %s ↔ %s = %.3f",
                    pair.agent_a,
                    pair.agent_b,
                    pair.correlation,
                )

        return snapshot

    def _determine_alert_level(
        self,
        high_corr_count: int,
        portfolio_score: float,
    ) -> CorrelationAlertLevel:
        """Determine alert level based on high correlation pairs and portfolio score."""
        # Check cooldown
        if self._last_alert_time:
            cooldown_end = self._last_alert_time + timedelta(
                hours=self._cfg.alert_cooldown_hours
            )
            if datetime.now(timezone.utc) < cooldown_end:
                return CorrelationAlertLevel.NORMAL

        if high_corr_count >= 3 or portfolio_score < self._cfg.critical_portfolio_score:
            self._last_alert_time = datetime.now(timezone.utc)
            return CorrelationAlertLevel.CRITICAL
        elif high_corr_count >= 1:
            self._last_alert_time = datetime.now(timezone.utc)
            return CorrelationAlertLevel.WARNING
        return CorrelationAlertLevel.NORMAL

    def _empty_snapshot(self) -> CorrelationSnapshot:
        """Return empty snapshot for disabled/error cases."""
        return CorrelationSnapshot(
            timestamp=datetime.now(timezone.utc),
            alert_level=CorrelationAlertLevel.NORMAL,
            portfolio_diversification_score=1.0,
            high_correlation_pairs=[],
            agent_count=0,
            analyzed_pairs=0,
            skipped_pairs=0,
        )

    async def get_latest_snapshot(self) -> CorrelationSnapshot | None:
        """Get most recent persisted correlation snapshot."""
        try:
            return await self._correlation_store.get_latest_snapshot()
        except Exception as exc:
            logger.warning("Failed to get latest correlation snapshot: %s", exc)
            return None

    async def get_agent_correlations(self, agent_name: str) -> list[CorrelationPair]:
        """Get all correlations for a specific agent from latest snapshot."""
        snapshot = await self.get_latest_snapshot()
        if not snapshot:
            return []

        return [
            pair
            for pair in snapshot.high_correlation_pairs
            if pair.agent_a == agent_name or pair.agent_b == agent_name
        ]

    def should_reduce_position(
        self,
        agent_name: str,
        snapshot: CorrelationSnapshot | None = None,
    ) -> tuple[bool, float]:
        """Check if an agent should reduce position due to correlation.

        Returns (should_reduce, multiplier) where multiplier is:
        - 1.0 = no reduction needed
        - 0.5 = reduce by 50% (2+ high-correlation pairs involving this agent)
        - 0.75 = reduce by 25% (1 high-correlation pair involving this agent)
        """
        if not snapshot or snapshot.alert_level == CorrelationAlertLevel.NORMAL:
            return False, 1.0

        # Count how many high-correlation pairs involve this agent
        involved_pairs = [
            pair
            for pair in snapshot.high_correlation_pairs
            if pair.agent_a == agent_name or pair.agent_b == agent_name
        ]

        if len(involved_pairs) >= 2:
            return True, 0.5
        elif len(involved_pairs) == 1:
            return True, 0.75
        return False, 1.0
