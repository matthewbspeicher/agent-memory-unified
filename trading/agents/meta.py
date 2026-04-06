from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from agents.manager import ManagerAgent
from agents.models import AgentConfig, AgentSignal

if TYPE_CHECKING:
    from agents.runner import AgentRunner
    from data.signal_bus import SignalBus

logger = logging.getLogger(__name__)


class MetaAgent(ManagerAgent):
    """
    Coordinates external signal ingestion with agent behavior.
    Subscribes to SignalBus and:
      1. Adjusts agent confidence thresholds (boost/suppress)
      2. Caches signals for opportunity annotation in the router
    """

    def __init__(
        self,
        config: AgentConfig,
        runner: AgentRunner,
        signal_bus: SignalBus,
    ) -> None:
        super().__init__(config)
        self._runner = runner
        self.signal_bus = signal_bus
        self.signal_bus.subscribe(self.handle_signal)

        self._boost_delta: float = config.parameters.get("boost_delta", 0.05)
        self._max_cumulative: float = config.parameters.get(
            "max_cumulative_boost", 0.15
        )
        self._boost_ttl_minutes: int = config.parameters.get("boost_ttl_minutes", 15)

        # Track active boosts: {agent_name: [(delta, expires_at, baseline_before_boost)]}
        self._active_boosts: dict[str, list[tuple[float, datetime, float]]] = {}
        # Signal cache for opportunity annotation: {ticker: [AgentSignal]}
        self._signal_cache: dict[str, list[AgentSignal]] = {}

    @property
    def description(self) -> str:
        return "Meta-intelligence agent: signal boost and opportunity annotation"

    async def evaluate_regime(self, data) -> dict[str, Any]:
        self._prune_signal_cache()
        self.decay_expired_boosts()
        return {
            "active_signals": sum(len(v) for v in self._signal_cache.values()),
            "boosted_agents": list(self._active_boosts.keys()),
            "signal_tickers": list(self._signal_cache.keys()),
        }

    async def handle_signal(self, signal: AgentSignal) -> None:
        ticker = signal.payload.get("ticker") or signal.payload.get("symbol")
        if not ticker:
            return

        direction = signal.payload.get("direction")
        if direction not in ("bullish", "bearish"):
            return

        # Cache for annotation
        self._signal_cache.setdefault(ticker, []).append(signal)

        # Apply confidence boosts to matching agents
        for agent_info in self._runner.list_agents():
            config = agent_info.config
            universe = config.universe
            if isinstance(universe, str):
                universe = [universe]

            if ticker not in universe:
                # Try fuzzy matching for Bittensor (e.g. BTCUSD vs BTC/USD)
                clean_ticker = ticker.replace("/", "").replace("-", "")
                if not any(
                    u.replace("/", "").replace("-", "") == clean_ticker
                    for u in universe
                ):
                    continue

            baseline = config.parameters.get("confidence_threshold", 0.7)
            current = config.runtime_overrides.get("confidence_threshold", baseline)

            # Calculate cumulative boost already applied
            cumulative = abs(current - baseline)
            if cumulative >= self._max_cumulative:
                logger.debug(
                    "MetaAgent: %s already at max cumulative boost (%.2f)",
                    agent_info.name,
                    cumulative,
                )
                continue

            # Special multiplier for Bittensor consensus
            boost_mult = 1.0
            if signal.signal_type == "bittensor_consensus":
                # Scale boost by consensus agreement ratio
                boost_mult = (
                    signal.payload.get("confidence", 1.0) * 2.0
                )  # up to 2x normal boost

            if direction == "bullish":
                delta = -self._boost_delta * boost_mult
            else:
                delta = self._boost_delta * boost_mult

            # Clamp to max cumulative
            new_cumulative = abs((current + delta) - baseline)
            if new_cumulative > self._max_cumulative:
                delta = (
                    -self._max_cumulative
                    if direction == "bullish"
                    else self._max_cumulative
                ) - (current - baseline)

            new_threshold = round(current + delta, 2)
            new_threshold = max(0.1, min(0.95, new_threshold))
            config.runtime_overrides["confidence_threshold"] = new_threshold

            self._active_boosts.setdefault(agent_info.name, []).append(
                (delta, signal.expires_at, current)
            )

            logger.info(
                "MetaAgent: %s boost %+.2f on %s (ticker=%s, %s). Threshold: %.2f -> %.2f",
                agent_info.name,
                delta,
                signal.signal_type,
                ticker,
                direction,
                current,
                new_threshold,
            )

    def decay_expired_boosts(self) -> None:
        now = datetime.now(timezone.utc)
        for agent_name in list(self._active_boosts.keys()):
            boosts = self._active_boosts[agent_name]
            expired = [b for b in boosts if b[1] <= now]
            remaining = [b for b in boosts if b[1] > now]

            if not expired:
                continue

            agent_info = self._runner.get_agent_info(agent_name)
            if not agent_info:
                self._active_boosts.pop(agent_name, None)
                continue

            config = agent_info.config
            current = config.runtime_overrides.get(
                "confidence_threshold",
                config.parameters.get("confidence_threshold", 0.7),
            )

            # Revert expired deltas
            revert = sum(b[0] for b in expired)
            new_threshold = round(current - revert, 2)
            new_threshold = max(0.1, min(0.95, new_threshold))

            if remaining:
                config.runtime_overrides["confidence_threshold"] = new_threshold
            else:
                config.runtime_overrides.pop("confidence_threshold", None)

            self._active_boosts[agent_name] = remaining
            if not remaining:
                self._active_boosts.pop(agent_name, None)

            logger.info(
                "MetaAgent: decayed %d expired boosts for %s. Threshold -> %.2f",
                len(expired),
                agent_name,
                config.runtime_overrides.get(
                    "confidence_threshold",
                    config.parameters.get("confidence_threshold", 0.7),
                ),
            )

    def get_signals_for_ticker(self, ticker: str) -> list[AgentSignal]:
        self._prune_signal_cache()
        return self._signal_cache.get(ticker, [])

    async def check_toxicity(self, ticker: str) -> float:
        """
        Scouts for 'toxic' volatility by polling social/news velocity.
        Returns a score 0.0 (clean) to 1.0 (highly toxic).
        """
        # 1. Check signal cache first (velocity of MetaAgent signals)
        recent_signals = self.get_signals_for_ticker(ticker)
        # Simple velocity heuristic: > 3 signals in cache = 0.5 toxicity
        signal_toxicity = min(0.5, len(recent_signals) * 0.15)

        # 2. External scout via opencli-rs (Subprocess)
        # This is Task 12 implementation
        external_toxicity = 0.0
        try:
            # Note: In production, we'd use a dedicated scout loop.
            # Here we do a quick check if no recent signals exist.
            if not recent_signals:
                # Mocking the opencli check for MVP; in Task 13 we'll wire the real binary
                pass
        except Exception as e:
            logger.warning(f"MetaAgent: Toxicity scout failed: {e}")

        final_score = min(1.0, signal_toxicity + external_toxicity)
        if final_score > 0.3:
            logger.warning(
                f"MetaAgent: Toxicity detected for {ticker}: {final_score:.2f}"
            )

        return final_score

    def _prune_signal_cache(self) -> None:
        now = datetime.now(timezone.utc)
        for ticker in list(self._signal_cache.keys()):
            self._signal_cache[ticker] = [
                s for s in self._signal_cache[ticker] if s.expires_at > now
            ]
            if not self._signal_cache[ticker]:
                del self._signal_cache[ticker]
