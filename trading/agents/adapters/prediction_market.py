from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from agents.models import AgentSignal
from agents.signal_adapter import SignalAdapter

if TYPE_CHECKING:
    from data.bus import DataBus

logger = logging.getLogger(__name__)


class PredictionMarketAdapter(SignalAdapter):
    """Watches Kalshi/Polymarket for volume spikes and price dislocations."""

    def __init__(
        self,
        data_bus: DataBus,
        volume_spike_threshold: float = 2.0,
        price_move_threshold: float = 0.10,
    ) -> None:
        self._data_bus = data_bus
        self._volume_spike_threshold = volume_spike_threshold
        self._price_move_threshold = price_move_threshold
        self._last_prices: dict[str, float] = {}

    def source_name(self) -> str:
        return "prediction_market"

    async def poll(self) -> list[AgentSignal]:
        signals: list[AgentSignal] = []
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=15)

        try:
            markets = await self._data_bus.get_kalshi_markets()
        except Exception as e:
            logger.error("PredictionMarketAdapter: failed to get markets: %s", e)
            return []

        for m in markets:
            ticker = m.get("ticker", "")
            volume = m.get("volume", 0)
            avg_volume = m.get("avg_volume", 0)
            yes_ask = m.get("yes_ask", 0.0)

            # Volume spike detection
            if avg_volume > 0:
                magnitude = volume / avg_volume
                if magnitude >= self._volume_spike_threshold:
                    signals.append(
                        AgentSignal(
                            source_agent=self.source_name(),
                            signal_type="volume_anomaly",
                            payload={
                                "ticker": ticker,
                                "magnitude": round(magnitude, 2),
                                "volume": volume,
                                "avg_volume": avg_volume,
                                "direction": "bullish" if yes_ask > 0.5 else "bearish",
                                "source": "kalshi",
                            },
                            expires_at=expires,
                        )
                    )

            # Price dislocation detection
            prev_price = self._last_prices.get(ticker)
            if prev_price is not None and prev_price > 0 and yes_ask > 0:
                move = abs(yes_ask - prev_price) / prev_price
                if move >= self._price_move_threshold:
                    direction = "bullish" if yes_ask > prev_price else "bearish"
                    signals.append(
                        AgentSignal(
                            source_agent=self.source_name(),
                            signal_type="price_dislocation",
                            payload={
                                "ticker": ticker,
                                "move_pct": round(move, 4),
                                "prev_price": prev_price,
                                "current_price": yes_ask,
                                "direction": direction,
                                "source": "kalshi",
                            },
                            expires_at=expires,
                        )
                    )
            self._last_prices[ticker] = yes_ask

        return signals
