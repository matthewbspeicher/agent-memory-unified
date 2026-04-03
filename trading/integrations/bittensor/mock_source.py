import asyncio
import random
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from integrations.bittensor.signals import BittensorSignalPayload, create_bittensor_agent_signal

if TYPE_CHECKING:
    from data.signal_bus import SignalBus

logger = logging.getLogger(__name__)

class MockBittensorSource:
    """Simulates Subnet 8 (Taoshi) signals for development and testing."""
    
    def __init__(self, signal_bus: 'SignalBus', symbols: list[str] = ["BTCUSD", "ETHUSD", "EURUSD"]):
        self._signal_bus = signal_bus
        self._symbols = symbols
        self._running = False

    async def start(self, interval_seconds: int = 30):
        """Start the mock signal emission loop."""
        self._running = True
        logger.info(f"MockBittensorSource started (interval: {interval_seconds}s)")
        while self._running:
            try:
                await self._emit_random_signal()
            except Exception as e:
                logger.error(f"MockBittensorSource error: {e}")
            await asyncio.sleep(interval_seconds)

    def stop(self):
        self._running = False

    async def _emit_random_signal(self):
        symbol = random.choice(self._symbols)
        direction = random.choice(["bullish", "bearish", "flat"])
        
        # Weighted direction: random float between -1 and 1
        weighted_dir = random.uniform(-1, 1)
        if weighted_dir > 0.3: direction = "bullish"
        elif weighted_dir < -0.3: direction = "bearish"
        else: direction = "flat"

        payload = BittensorSignalPayload(
            symbol=symbol,
            timeframe="5m",
            direction=direction,
            confidence=random.uniform(0.5, 0.95),
            expected_return=random.uniform(0.005, 0.03),
            window_id=f"mock-{int(datetime.now(timezone.utc).timestamp())}",
            miner_count=random.randint(50, 150)
        )

        signal = create_bittensor_agent_signal(payload)
        logger.info(f"MockBittensorSource: Emitting {direction} signal for {symbol}")
        await self._signal_bus.publish(signal)
