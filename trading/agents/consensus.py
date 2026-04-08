# agents/consensus.py
"""
Enhanced multi-agent consensus system with weighted voting, quorum rules,
and regime-aware thresholds.

Extends the basic N-of-M ConsensusRouter with:
- Weighted votes (by agent confidence, Sharpe ratio, ELO rating)
- Configurable quorum (minimum weight percentage, not just raw count)
- Regime-aware consensus thresholds
- Performance-based vote weight decay
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


from agents.models import ActionLevel, Opportunity

logger = logging.getLogger(__name__)


class WeightSource(str, Enum):
    """How to compute vote weight for each agent."""

    EQUAL = "equal"  # All votes count equally (legacy behavior)
    CONFIDENCE = "confidence"  # Weight by opportunity.confidence
    SHARPE = "sharpe"  # Weight by agent's historical Sharpe ratio
    ELO = "elo"  # Weight by agent's ELO rating
    COMPOSITE = "composite"  # Weighted blend of confidence + Sharpe + ELO


@dataclass
class AgentWeightProfile:
    """Performance profile for weighting an agent's vote."""

    agent_name: str
    sharpe_ratio: float = 0.0
    elo_rating: int = 1000
    total_trades: int = 0
    win_rate: float = 0.0
    updated_at: datetime | None = None

    def composite_score(self) -> float:
        """Compute a normalized 0-1 composite performance score."""
        # Sharpe: typically -2 to 4, normalize to 0-1
        sharpe_norm = max(0.0, min(1.0, (self.sharpe_ratio + 2) / 6))
        # ELO: typically 800-2200, normalize to 0-1
        elo_norm = max(0.0, min(1.0, (self.elo_rating - 800) / 1400))
        # Win rate: 0-100, normalize to 0-1
        win_norm = max(0.0, min(1.0, self.win_rate / 100))
        # Trade count weight: log-scale, caps at 500 trades
        count_weight = min(1.0, (self.total_trades**0.5) / (500**0.5))

        return (
            0.35 * sharpe_norm + 0.30 * elo_norm + 0.20 * win_norm + 0.15 * count_weight
        )


@dataclass
class ConsensusConfig:
    """Configuration for enhanced consensus routing."""

    # Base threshold: minimum number of agreeing agents
    threshold: int = 2

    # Weight threshold: minimum total vote weight required (0.0-1.0)
    # If set, overrides raw threshold when weight voting is used
    weight_threshold: float = 0.0

    # Time window for collecting votes
    window_minutes: int = 15

    # Weight calculation method
    weight_source: WeightSource = WeightSource.EQUAL

    # Composite weight blending (only used when weight_source=COMPOSITE)
    confidence_weight: float = 0.5
    sharpe_weight: float = 0.3
    elo_weight: float = 0.2

    # Regime-specific thresholds: {regime_value: threshold}
    # e.g. {"high_volatility": 4, "crisis": 5}
    regime_thresholds: dict[str, int] = field(default_factory=dict)

    # Minimum agents required before consensus can be reached
    min_agents: int = 1

    # Maximum age (minutes) for an agent's weight profile before it's considered stale
    profile_max_age_minutes: int = 1440  # 24 hours

    # Enable/disable consensus (if disabled, passes through directly)
    enabled: bool = True

    # Require unanimous vote for certain regimes
    unanimous_regimes: list[str] = field(default_factory=list)


@dataclass
class VoteRecord:
    """A single vote in the consensus system."""

    agent_name: str
    symbol: str
    side: str
    opportunity_id: str
    confidence: float
    weight: float
    timestamp: datetime
    regime: str | None = None


class ConsensusStore:
    """Persistent storage for consensus votes (SQLite-backed)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def add_vote(
        self,
        symbol: str,
        side: str,
        agent_name: str,
        opportunity_id: str,
        weight: float,
        timestamp: datetime,
        regime: str | None = None,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO consensus_votes
                (symbol, side, agent_name, opportunity_id, weight, timestamp, regime)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                side,
                agent_name,
                opportunity_id,
                weight,
                timestamp.isoformat(),
                regime,
            ),
        )
        await self._db.commit()

    async def get_votes(
        self,
        symbol: str,
        side: str,
        cutoff: datetime,
    ) -> list[VoteRecord]:
        rows = await self._db.fetch_all(
            """
            SELECT agent_name, symbol, side, opportunity_id, weight, timestamp, regime
            FROM consensus_votes
            WHERE symbol = ? AND side = ? AND timestamp >= ?
            ORDER BY timestamp DESC
            """,
            (symbol, side, cutoff.isoformat()),
        )
        return [
            VoteRecord(
                agent_name=r["agent_name"],
                symbol=r["symbol"],
                side=r["side"],
                opportunity_id=r["opportunity_id"],
                confidence=0.0,  # not stored
                weight=float(r["weight"]),
                timestamp=datetime.fromisoformat(r["timestamp"]),
                regime=r["regime"],
            )
            for r in rows
        ]

    async def clear_votes(self, symbol: str, side: str) -> None:
        await self._db.execute(
            "DELETE FROM consensus_votes WHERE symbol = ? AND side = ?",
            (symbol, side),
        )
        await self._db.commit()

    async def cleanup_expired(self, cutoff: datetime) -> None:
        await self._db.execute(
            "DELETE FROM consensus_votes WHERE timestamp < ?",
            (cutoff.isoformat(),),
        )
        await self._db.commit()


class AgentWeightProvider:
    """Provides agent weight profiles for consensus vote weighting.

    In production, this pulls from the leaderboard engine and trade analytics.
    In backtesting, weights can be injected directly.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, AgentWeightProfile] = {}

    def update_profile(self, profile: AgentWeightProfile) -> None:
        self._profiles[profile.agent_name] = profile

    def get_profile(self, agent_name: str) -> AgentWeightProfile | None:
        return self._profiles.get(agent_name)

    def load_from_leaderboard(self, rankings: list[dict[str, Any]]) -> None:
        """Load profiles from leaderboard engine output."""
        for r in rankings:
            self._profiles[r["agent_name"]] = AgentWeightProfile(
                agent_name=r["agent_name"],
                sharpe_ratio=float(r.get("sharpe_ratio", 0)),
                elo_rating=int(r.get("elo", 1000)),
                total_trades=int(r.get("total_trades", 0)),
                win_rate=float(r.get("win_rate", 0)),
                updated_at=datetime.now(timezone.utc),
            )

    def _tier_weight_multiplier(self, elo: int) -> float:
        """Competition tier affects vote weight."""
        if elo >= 1400:
            return 1.5   # Diamond
        if elo >= 1200:
            return 1.0   # Gold
        if elo >= 1000:
            return 0.8   # Silver
        return 0.0        # Bronze = shadow mode (no weight)

    def compute_vote_weight(
        self,
        opportunity: Opportunity,
        config: ConsensusConfig,
    ) -> float:
        """Compute the weight for an agent's vote based on config."""
        agent_name = opportunity.agent_name

        if config.weight_source == WeightSource.EQUAL:
            return 1.0

        if config.weight_source == WeightSource.CONFIDENCE:
            return max(0.01, opportunity.confidence)

        profile = self.get_profile(agent_name)
        if profile is None:
            # Unknown agent — use confidence as fallback
            return max(0.01, opportunity.confidence)

        if config.weight_source == WeightSource.SHARPE:
            # Normalize Sharpe to 0-1 range (Sharpe typically -2 to 4)
            return max(0.01, min(1.0, (profile.sharpe_ratio + 2) / 6))

        if config.weight_source == WeightSource.ELO:
            # Normalize ELO to 0-1 range (ELO typically 800-2200)
            base = max(0.01, min(1.0, (profile.elo_rating - 800) / 1400))
            return base * self._tier_weight_multiplier(profile.elo_rating)

        if config.weight_source == WeightSource.COMPOSITE:
            # Blend confidence with historical performance
            conf = max(0.01, opportunity.confidence)
            sharpe_score = max(0.01, min(1.0, (profile.sharpe_ratio + 2) / 6))
            # Composite mode uses a slightly wider ELO range so historical
            # performance tempers confidence without dominating it.
            elo_score = max(0.01, min(1.0, (profile.elo_rating - 800) / 1600))
            blended = (
                config.confidence_weight * conf
                + config.sharpe_weight * sharpe_score
                + config.elo_weight * elo_score
            )
            return max(0.01, min(1.0, blended)) * self._tier_weight_multiplier(profile.elo_rating)

        return 1.0


class EnhancedConsensusRouter:
    """
    Enhanced consensus router with weighted voting, quorum rules, and
    regime-aware thresholds.

    Wraps an OpportunityRouter (or any route()-callable) and collects
    votes from multiple agents before elevating to AUTO_EXECUTE.

    Usage:
        weight_provider = AgentWeightProvider()
        weight_provider.load_from_leaderboard(leaderboard_rankings)

        config = ConsensusConfig(
            threshold=2,
            weight_source=WeightSource.COMPOSITE,
            weight_threshold=0.6,
            regime_thresholds={"high_volatility": 4},
        )

        consensus = EnhancedConsensusRouter(
            target_router=router,
            config=config,
            weight_provider=weight_provider,
        )

        await consensus.route(opportunity, action_level)
    """

    def __init__(
        self,
        target_router: Any,
        config: ConsensusConfig | None = None,
        weight_provider: AgentWeightProvider | None = None,
        consensus_store: ConsensusStore | None = None,
    ) -> None:
        self._target = target_router
        self._config = config or ConsensusConfig()
        self._weight_provider = weight_provider or AgentWeightProvider()
        self._store = consensus_store

        # In-memory fallback: (ticker, side) -> {agent_name: VoteRecord}
        self._pending: dict[tuple[str, str], dict[str, VoteRecord]] = defaultdict(dict)

    async def route(self, opportunity: Opportunity, action_level: ActionLevel) -> None:
        """Main routing entry point. Collects vote and checks consensus."""
        if not self._config.enabled:
            await self._target.route(opportunity, action_level)
            return

        if not opportunity.suggested_trade:
            await self._target.route(opportunity, action_level)
            return

        if (
            action_level != ActionLevel.SUGGEST_TRADE
            and action_level != ActionLevel.AUTO_EXECUTE
        ):
            await self._target.route(opportunity, action_level)
            return

        now = opportunity.timestamp
        if not now.tzinfo:
            now = now.replace(tzinfo=timezone.utc)

        side = opportunity.suggested_trade.side.value
        key = (opportunity.symbol.ticker, side)

        # Compute vote weight
        weight = self._weight_provider.compute_vote_weight(opportunity, self._config)

        # Get regime for threshold lookup
        regime = self._get_regime(opportunity)

        if self._store is not None:
            await self._route_persistent(
                opportunity, action_level, key, side, weight, regime, now
            )
        else:
            await self._route_in_memory(
                opportunity, action_level, key, side, weight, regime, now
            )

    def _get_regime(self, opportunity: Opportunity) -> str | None:
        """Extract regime value from opportunity data."""
        regime_data = opportunity.data.get("regime")
        if isinstance(regime_data, str):
            return regime_data or None
        if isinstance(regime_data, dict):
            trend = regime_data.get("trend", "")
            vol = regime_data.get("volatility", "")
            if vol == "high":
                return "high_volatility"
            if vol == "low":
                return "low_volatility"

            # Use trend + volatility composite if available
            if trend and vol:
                return f"{trend}_{vol}"
            return trend or vol or None
        return None

    def _get_threshold(self, regime: str | None) -> int:
        """Get consensus threshold, potentially regime-adjusted."""
        if regime and regime in self._config.regime_thresholds:
            return self._config.regime_thresholds[regime]
        return self._config.threshold

    def _is_unanimous_required(self, regime: str | None) -> bool:
        """Check if unanimous voting is required for this regime."""
        if regime and regime in self._config.unanimous_regimes:
            return True
        return False

    async def _route_persistent(
        self,
        opportunity: Opportunity,
        action_level: ActionLevel,
        key: tuple[str, str],
        side: str,
        weight: float,
        regime: str | None,
        now: datetime,
    ) -> None:
        """Route using persistent vote storage."""
        cutoff = now - timedelta(minutes=self._config.window_minutes)
        await self._store.cleanup_expired(cutoff)
        await self._store.add_vote(
            symbol=key[0],
            side=side,
            agent_name=opportunity.agent_name,
            opportunity_id=str(opportunity.id),
            weight=weight,
            timestamp=now,
            regime=regime,
        )

        votes = await self._store.get_votes(key[0], side, cutoff)
        if self._check_consensus(votes, regime, now):
            await self._store.clear_votes(key[0], side)
            await self._execute_consensus(opportunity, votes, regime)
        else:
            await self._target.route(opportunity, action_level)

    async def _route_in_memory(
        self,
        opportunity: Opportunity,
        action_level: ActionLevel,
        key: tuple[str, str],
        side: str,
        weight: float,
        regime: str | None,
        now: datetime,
    ) -> None:
        """Route using in-memory vote storage."""
        record = VoteRecord(
            agent_name=opportunity.agent_name,
            symbol=key[0],
            side=side,
            opportunity_id=str(opportunity.id),
            confidence=opportunity.confidence,
            weight=weight,
            timestamp=now,
            regime=regime,
        )
        self._pending[key][opportunity.agent_name] = record

        # Filter out expired votes
        cutoff = now - timedelta(minutes=self._config.window_minutes)
        valid = {
            name: v for name, v in self._pending[key].items() if v.timestamp >= cutoff
        }
        self._pending[key] = valid

        votes = list(valid.values())
        if self._check_consensus(votes, regime, now):
            self._pending[key].clear()
            await self._execute_consensus(opportunity, votes, regime)
        else:
            await self._target.route(opportunity, action_level)

    def _check_consensus(
        self,
        votes: list[VoteRecord],
        regime: str | None,
        now: datetime,
    ) -> bool:
        """Check if consensus conditions are met."""
        if not votes:
            return False

        threshold = self._get_threshold(regime)
        total_weight = sum(v.weight for v in votes)
        unique_agents = len(votes)

        # Minimum agents check
        if unique_agents < max(self._config.min_agents, 1):
            return False

        # Unanimous check
        if self._is_unanimous_required(regime):
            # For unanimous, we need weight_threshold or raw threshold
            if self._config.weight_threshold > 0:
                return total_weight >= self._config.weight_threshold * unique_agents
            return unique_agents >= threshold

        # Weight-threshold mode: require X% of theoretical max weight
        if self._config.weight_threshold > 0:
            # Theoretical max weight = number of agents * max possible weight per agent
            # For simplicity, use unique_agents as proxy for max
            weight_ratio = total_weight / max(unique_agents, 1)
            return (
                weight_ratio >= self._config.weight_threshold
                and unique_agents >= threshold
            )

        # Raw count mode (legacy behavior)
        return unique_agents >= threshold

    async def _execute_consensus(
        self,
        opportunity: Opportunity,
        votes: list[VoteRecord],
        regime: str | None,
    ) -> None:
        """Consensus reached — elevate to AUTO_EXECUTE."""
        total_weight = sum(v.weight for v in votes)
        agent_names = [v.agent_name for v in votes]

        logger.info(
            "Enhanced consensus reached for %s %s: %d agents, total_weight=%.3f, regime=%s",
            opportunity.symbol.ticker,
            opportunity.suggested_trade.side.value
            if opportunity.suggested_trade
            else "?",
            len(votes),
            total_weight,
            regime,
        )

        # Annotate reasoning
        consensus_note = (
            f" [Consensus: {len(votes)} agents, weight={total_weight:.2f}"
            f", agents={','.join(agent_names)}"
        )
        if regime:
            consensus_note += f", regime={regime}"
        consensus_note += "]"
        opportunity.reasoning += consensus_note

        # Publish consensus event
        event_bus = getattr(self._target, "_event_bus", None)
        if event_bus:
            try:
                await event_bus.publish(
                    "consensus",
                    {
                        "symbol": opportunity.symbol.ticker,
                        "side": opportunity.suggested_trade.side.value
                        if opportunity.suggested_trade
                        else "",
                        "agent_count": len(votes),
                        "total_weight": total_weight,
                        "agents": agent_names,
                        "regime": regime,
                        "opportunity_id": str(opportunity.id),
                    },
                )
            except Exception:
                pass

        await self._target.route(opportunity, ActionLevel.AUTO_EXECUTE)

    # --- Backtesting support ---

    def collect_vote(
        self,
        opportunity: Opportunity,
        regime: str | None = None,
    ) -> VoteRecord:
        """Collect a vote without routing (for backtesting integration)."""
        weight = self._weight_provider.compute_vote_weight(opportunity, self._config)
        now = opportunity.timestamp
        if not now.tzinfo:
            now = now.replace(tzinfo=timezone.utc)

        return VoteRecord(
            agent_name=opportunity.agent_name,
            symbol=opportunity.symbol.ticker,
            side=opportunity.suggested_trade.side.value
            if opportunity.suggested_trade
            else "",
            opportunity_id=str(opportunity.id),
            confidence=opportunity.confidence,
            weight=weight,
            timestamp=now,
            regime=regime,
        )

    def check_votes_consensus(
        self,
        votes: list[VoteRecord],
        regime: str | None = None,
    ) -> tuple[bool, float, str]:
        """
        Check if a list of votes reaches consensus (for backtesting).

        Returns:
            (consensus_reached, total_weight, reason)
        """
        if not votes:
            return False, 0.0, "no_votes"

        datetime.now(timezone.utc)
        threshold = self._get_threshold(regime)
        total_weight = sum(v.weight for v in votes)
        unique_agents = len(set(v.agent_name for v in votes))

        if unique_agents < max(self._config.min_agents, 1):
            return (
                False,
                total_weight,
                f"insufficient_agents:{unique_agents}<{self._config.min_agents}",
            )

        if self._is_unanimous_required(regime):
            if unique_agents >= threshold:
                return True, total_weight, "unanimous_reached"
            return False, total_weight, "unanimous_required"

        if self._config.weight_threshold > 0:
            weight_ratio = total_weight / max(unique_agents, 1)
            if (
                weight_ratio >= self._config.weight_threshold
                and unique_agents >= threshold
            ):
                return (
                    True,
                    total_weight,
                    f"weight_threshold_met:{weight_ratio:.2f}>= {self._config.weight_threshold}",
                )
            return (
                False,
                total_weight,
                f"weight_threshold_not_met:{weight_ratio:.2f}< {self._config.weight_threshold}",
            )

        if unique_agents >= threshold:
            return (
                True,
                total_weight,
                f"count_threshold_met:{unique_agents}>= {threshold}",
            )
        return (
            False,
            total_weight,
            f"count_threshold_not_met:{unique_agents}< {threshold}",
        )
