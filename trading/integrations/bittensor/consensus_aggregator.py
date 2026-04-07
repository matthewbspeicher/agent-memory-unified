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

    def __init__(self, signal_bus: SignalBus, window_minutes: int = 5):
        self.signal_bus = signal_bus
        self.window_minutes = window_minutes
        # Store as: symbol -> hotkey -> (timestamp, payload)
        self.positions: dict[str, dict[str, tuple[datetime, dict]]] = defaultdict(dict)
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self):
        self._running = True
        self.signal_bus.subscribe(self._handle_miner_position)
        logger.info(f"MinerConsensusAggregator started (window: {self.window_minutes}m)")

    async def stop(self):
        self._running = False

    async def _handle_miner_position(self, signal: AgentSignal):
        if signal.signal_type != "bittensor_miner_position":
            return
        
        payload = signal.payload
        symbol = payload.get("symbol")
        hotkey = payload.get("miner_hotkey")
        open_ms = payload.get("open_ms", 0)

        if not symbol or not hotkey:
            return

        open_time = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc)

        async with self._lock:
            self.positions[symbol][hotkey] = (open_time, payload)
            await self._evaluate_consensus(symbol)

    async def _evaluate_consensus(self, symbol: str):
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(minutes=self.window_minutes)

        symbol_positions = self.positions[symbol]
        active_positions = {}

        for hotkey, (pos_time, payload) in list(symbol_positions.items()):
            if pos_time >= cutoff_time:
                active_positions[hotkey] = payload
            else:
                del symbol_positions[hotkey]

        if not active_positions:
            return

        direction_counts = {"long": 0, "short": 0, "flat": 0}
        total_leverage = 0.0

        for payload in active_positions.values():
            direction = payload.get("direction", "flat")
            if direction in direction_counts:
                direction_counts[direction] += 1
            total_leverage += payload.get("leverage", 0.0)

        total_miners = len(active_positions)
        if total_miners == 0:
            return

        # Determine majority
        majority_dir = max(direction_counts.items(), key=lambda x: x[1])
        dir_name, count = majority_dir

        if count == 0:
            return

        confidence = count / total_miners
        avg_leverage = total_leverage / total_miners

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
            expected_return=avg_leverage,  # using average leverage as a proxy
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
