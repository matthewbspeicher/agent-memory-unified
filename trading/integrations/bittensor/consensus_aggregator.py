import asyncio
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from data.signal_bus import SignalBus
from agents.models import AgentSignal
from integrations.bittensor.signals import BittensorSignalPayload, create_bittensor_agent_signal

logger = logging.getLogger(__name__)

class MinerConsensusAggregator:
    """Aggregates individual bittensor_miner_position signals into bittensor_consensus signals."""

    def __init__(self, signal_bus: SignalBus, store: BittensorStore | None = None, window_minutes: int = 5):
        self.signal_bus = signal_bus
        self.store = store
        self.window_minutes = window_minutes
        # Store as: symbol -> hotkey -> (timestamp, payload)
        self.positions: dict[str, dict[str, tuple[datetime, dict]]] = defaultdict(dict)
        self._running = False
        self._lock = asyncio.Lock()
        self._reference_time: datetime | None = None
        self._miner_weights: dict[str, float] = {}
        self._weights_last_updated: datetime | None = None

    async def _refresh_weights(self):
        """Fetch latest miner rankings and cache them as weights."""
        if not self.store:
            return
        
        now = datetime.now(timezone.utc)
        if self._weights_last_updated and (now - self._weights_last_updated).total_seconds() < 300:
            return # cache for 5 mins

        try:
            rankings = await self.store.get_miner_rankings(limit=256)
            new_weights = {r.miner_hotkey: r.hybrid_score for r in rankings}
            self._miner_weights = new_weights
            self._weights_last_updated = now
            logger.info("Refreshed consensus weights for %d miners", len(new_weights))
        except Exception as e:
            logger.warning("Failed to refresh consensus weights: %s", e)

    async def _evaluate_consensus(self, symbol: str):
        now = self._reference_time or datetime.now(timezone.utc)
        cutoff_time = now - timedelta(minutes=self.window_minutes)

        await self._refresh_weights()

        symbol_positions = self.positions[symbol]
        active_positions = {}

        for hotkey, (pos_time, payload) in list(symbol_positions.items()):
            if pos_time >= cutoff_time:
                active_positions[hotkey] = payload
            else:
                del symbol_positions[hotkey]

        if not active_positions:
            return

        direction_scores = {"long": 0.0, "short": 0.0, "flat": 0.0}
        total_weight = 0.0

        for hotkey, payload in active_positions.items():
            direction = payload.get("direction", "flat")
            # Default to 0.5 weight if miner has no ranking yet
            weight = self._miner_weights.get(hotkey, 0.5)
            
            if direction in direction_scores:
                direction_scores[direction] += weight
            
            total_weight += weight

        total_miners = len(active_positions)
        if total_weight == 0:
            return

        # Determine majority by weighted score
        majority_dir = max(direction_scores.items(), key=lambda x: x[1])
        dir_name, weighted_count = majority_dir

        if weighted_count == 0:
            return

        # Weighted confidence
        confidence = weighted_count / total_weight
        
        # Leveraged expected return proxy (unweighted average for now)
        avg_leverage = sum(p.get("leverage", 0.0) for p in active_positions.values()) / total_miners

        # Map to expected consensus directions
        mapped_direction = "flat"
        if dir_name == "long":
            mapped_direction = "bullish"
        elif dir_name == "short":
            mapped_direction = "bearish"

        window_id = now.strftime("%Y%m%d-%H%M")

        consensus_payload = BittensorSignalPayload(
            symbol=symbol,
            timeframe="5m",
            direction=mapped_direction,
            confidence=confidence,
            expected_return=avg_leverage,
            window_id=window_id,
            miner_count=total_miners
        )

        consensus_signal = create_bittensor_agent_signal(
            payload=consensus_payload,
            source_agent="miner_consensus_aggregator",
            ttl_minutes=30
        )

        await self.signal_bus.publish(consensus_signal)

    def get_status(self) -> dict:
        """Returns the current aggregation state for monitoring."""
        status = {}
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(minutes=self.window_minutes)

        for symbol, hotkeys in self.positions.items():
            active_count = sum(1 for pos_time, _ in hotkeys.values() if pos_time >= cutoff_time)
            if active_count > 0:
                status[symbol] = {"active_miners": active_count}
                
        return status
