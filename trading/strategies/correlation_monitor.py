# strategies/correlation_monitor.py
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
class AgentSignalRecord:
    """Record of a signal from an agent."""

    agent_name: str
    symbol: str
    signal: str  # "buy", "sell", "hold"
    confidence: float
    timestamp: datetime


@dataclass
class CorrelationResult:
    """Correlation between two agents over a time window."""

    agent_a: str
    agent_b: str
    correlation: float  # -1 to 1
    sample_count: int
    agreement_rate: float  # % of time they agree on direction
    window_minutes: int


class StrategyCorrelationMonitor(StructuredAgent):
    """Monitors correlation between different agents' signals.

    Tracks when multiple agents generate signals for the same symbols
    and alerts when correlation exceeds threshold (redundancy risk).

    Parameters:
        correlation_window_minutes: Time window for correlation calculation. Default 60.
        high_correlation_threshold: Alert when correlation exceeds this. Default 0.8.
        min_samples: Minimum samples needed for correlation. Default 10.
        alert_cooldown_minutes: Minimum time between alerts for same pair. Default 30.
    """

    # Store for recent signals across all agents (class-level for cross-instance sharing)
    _signal_history: dict[str, list[AgentSignalRecord]] = defaultdict(list)
    _last_alerts: dict[str, datetime] = {}

    @property
    def description(self) -> str:
        threshold = self.parameters.get("high_correlation_threshold", 0.8)
        return f"Strategy correlation monitor (threshold={threshold})"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        """Monitor correlation between agents and generate alerts."""
        params = self.parameters
        window_minutes = params.get("correlation_window_minutes", 60)
        high_threshold = params.get("high_correlation_threshold", 0.8)
        min_samples = params.get("min_samples", 10)
        cooldown_minutes = params.get("alert_cooldown_minutes", 30)

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

        # Prune old signals
        self._prune_signals(cutoff)

        # Get all agents that have recent signals
        active_agents = self._get_active_agents(cutoff)
        if len(active_agents) < 2:
            return []

        opportunities: list[Opportunity] = []
        alerts_generated = []

        # Check correlation between all pairs
        for i, agent_a in enumerate(active_agents):
            for agent_b in active_agents[i + 1 :]:
                correlation = self._calculate_correlation(
                    agent_a, agent_b, cutoff, min_samples
                )

                if correlation is None:
                    continue

                # Check if correlation exceeds threshold
                if abs(correlation.correlation) >= high_threshold:
                    pair_key = f"{agent_a}:{agent_b}"

                    # Check cooldown
                    last_alert = self._last_alerts.get(pair_key)
                    now = datetime.now(timezone.utc)

                    if (
                        last_alert
                        and (now - last_alert).total_seconds() < cooldown_minutes * 60
                    ):
                        continue

                    # Generate alert opportunity
                    direction = (
                        "positive" if correlation.correlation > 0 else "negative"
                    )
                    signal_type = "sell" if correlation.correlation > 0 else "buy"

                    opp = Opportunity(
                        id=str(uuid.uuid4()),
                        agent_name=self.name,
                        symbol=Symbol(ticker="MULTI", asset_type=None),
                        signal=signal_type,
                        confidence=abs(correlation.correlation),
                        reasoning=(
                            f"High {direction} correlation ({correlation.correlation:.2f}) "
                            f"detected between {agent_a} and {agent_b}. "
                            f"Agreement rate: {correlation.agreement_rate:.1%}. "
                            f"This indicates signal redundancy - consider adjusting one strategy."
                        ),
                        data={
                            "correlation": correlation.correlation,
                            "agreement_rate": correlation.agreement_rate,
                            "agent_a": agent_a,
                            "agent_b": agent_b,
                            "sample_count": correlation.sample_count,
                            "window_minutes": window_minutes,
                            "alert_type": "high_correlation",
                        },
                        timestamp=now,
                    )
                    opportunities.append(opp)
                    self._last_alerts[pair_key] = now
                    alerts_generated.append(pair_key)

        if alerts_generated:
            logger.info(
                "Correlation monitor generated %d alerts for %s",
                len(alerts_generated),
                alerts_generated,
            )

        return opportunities

    def _prune_signals(self, cutoff: datetime) -> None:
        """Remove signals older than cutoff."""
        for agent_name in list(self._signal_history.keys()):
            self._signal_history[agent_name] = [
                s for s in self._signal_history[agent_name] if s.timestamp >= cutoff
            ]
            if not self._signal_history[agent_name]:
                del self._signal_history[agent_name]

    def _get_active_agents(self, cutoff: datetime) -> list[str]:
        """Get agents with recent signals."""
        return [
            agent_name
            for agent_name, signals in self._signal_history.items()
            if signals and any(s.timestamp >= cutoff for s in signals)
        ]

    def _calculate_correlation(
        self,
        agent_a: str,
        agent_b: str,
        cutoff: datetime,
        min_samples: int,
    ) -> CorrelationResult | None:
        """Calculate correlation between two agents' signals."""
        signals_a = [
            s for s in self._signal_history.get(agent_a, []) if s.timestamp >= cutoff
        ]
        signals_b = [
            s for s in self._signal_history.get(agent_b, []) if s.timestamp >= cutoff
        ]

        # Find overlapping symbols
        symbols_a = {s.symbol for s in signals_a}
        symbols_b = {s.symbol for s in signals_b}
        common_symbols = symbols_a & symbols_b

        if len(common_symbols) < min_samples:
            return None

        # For each common symbol, compare most recent signals
        agreements = 0
        disagreements = 0
        correlation_pairs = []  # (signal_a_numeric, signal_b_numeric)

        signal_map_a = {s.symbol: s for s in signals_a}
        signal_map_b = {s.symbol: s for s in signals_b}

        for symbol in common_symbols:
            sa = signal_map_a.get(symbol)
            sb = signal_map_b.get(symbol)

            if sa is None or sb is None:
                continue

            # Convert signals to numeric: buy=1, sell=-1, hold=0
            a_val = self._signal_to_numeric(sa.signal)
            b_val = self._signal_to_numeric(sb.signal)

            correlation_pairs.append((a_val, b_val))

            if a_val == b_val:
                agreements += 1
            elif a_val != 0 and b_val != 0:  # Both have direction
                disagreements += 1

        total_directional = agreements + disagreements
        if total_directional == 0:
            return None

        agreement_rate = (
            agreements / total_directional if total_directional > 0 else 0.0
        )

        # Calculate Pearson correlation
        correlation = self._pearson_correlation(correlation_pairs)

        return CorrelationResult(
            agent_a=agent_a,
            agent_b=agent_b,
            correlation=correlation,
            sample_count=len(correlation_pairs),
            agreement_rate=agreement_rate,
            window_minutes=0,  # Will be set by caller
        )

    @staticmethod
    def _signal_to_numeric(signal: str) -> float:
        """Convert signal string to numeric value."""
        signal_lower = signal.lower()
        if signal_lower == "buy":
            return 1.0
        elif signal_lower == "sell":
            return -1.0
        return 0.0

    @staticmethod
    def _pearson_correlation(pairs: list[tuple[float, float]]) -> float:
        """Calculate Pearson correlation coefficient."""
        if len(pairs) < 2:
            return 0.0

        n = len(pairs)
        sum_a = sum(p[0] for p in pairs)
        sum_b = sum(p[1] for p in pairs)
        sum_ab = sum(p[0] * p[1] for p in pairs)
        sum_a2 = sum(p[0] ** 2 for p in pairs)
        sum_b2 = sum(p[1] ** 2 for p in pairs)

        numerator = n * sum_ab - sum_a * sum_b
        denominator = ((n * sum_a2 - sum_a**2) * (n * sum_b2 - sum_b**2)) ** 0.5

        if denominator == 0:
            return 0.0

        return numerator / denominator

    @classmethod
    def record_signal(
        cls,
        agent_name: str,
        symbol: str,
        signal: str,
        confidence: float,
    ) -> None:
        """Record a signal from an agent (called externally)."""
        record = AgentSignalRecord(
            agent_name=agent_name,
            symbol=symbol,
            signal=signal,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )
        cls._signal_history[agent_name].append(record)

        # Keep history bounded (last 1000 signals per agent)
        if len(cls._signal_history[agent_name]) > 1000:
            cls._signal_history[agent_name] = cls._signal_history[agent_name][-1000:]

    @classmethod
    def get_correlation_matrix(cls, window_minutes: int = 60) -> dict[str, Any]:
        """Get current correlation matrix for all active agents."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        active_agents = cls._get_active_agents_static(cutoff)

        matrix: dict[str, dict[str, float]] = {}
        for agent_a in active_agents:
            matrix[agent_a] = {}
            for agent_b in active_agents:
                if agent_a == agent_b:
                    matrix[agent_a][agent_b] = 1.0
                else:
                    result = cls._calculate_correlation_static(
                        agent_a, agent_b, cutoff, 1
                    )
                    matrix[agent_a][agent_b] = result.correlation if result else 0.0

        return {
            "agents": active_agents,
            "matrix": matrix,
            "window_minutes": window_minutes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def _get_active_agents_static(cls, cutoff: datetime) -> list[str]:
        """Get agents with recent signals (static version)."""
        return [
            agent_name
            for agent_name, signals in cls._signal_history.items()
            if signals and any(s.timestamp >= cutoff for s in signals)
        ]

    @classmethod
    def _calculate_correlation_static(
        cls,
        agent_a: str,
        agent_b: str,
        cutoff: datetime,
        min_samples: int,
    ) -> CorrelationResult | None:
        """Calculate correlation (static version for external access)."""
        signals_a = [
            s for s in cls._signal_history.get(agent_a, []) if s.timestamp >= cutoff
        ]
        signals_b = [
            s for s in cls._signal_history.get(agent_b, []) if s.timestamp >= cutoff
        ]

        symbols_a = {s.symbol for s in signals_a}
        symbols_b = {s.symbol for s in signals_b}
        common_symbols = symbols_a & symbols_b

        if len(common_symbols) < min_samples:
            return None

        signal_map_a = {s.symbol: s for s in signals_a}
        signal_map_b = {s.symbol: s for s in signals_b}

        agreements = 0
        disagreements = 0
        correlation_pairs = []

        for symbol in common_symbols:
            sa = signal_map_a.get(symbol)
            sb = signal_map_b.get(symbol)

            if sa is None or sb is None:
                continue

            a_val = cls._signal_to_numeric(sa.signal)
            b_val = cls._signal_to_numeric(sb.signal)

            correlation_pairs.append((a_val, b_val))

            if a_val == b_val:
                agreements += 1
            elif a_val != 0 and b_val != 0:
                disagreements += 1

        total_directional = agreements + disagreements
        agreement_rate = (
            agreements / total_directional if total_directional > 0 else 0.0
        )
        correlation = cls._pearson_correlation(correlation_pairs)

        return CorrelationResult(
            agent_a=agent_a,
            agent_b=agent_b,
            correlation=correlation,
            sample_count=len(correlation_pairs),
            agreement_rate=agreement_rate,
            window_minutes=0,
        )
