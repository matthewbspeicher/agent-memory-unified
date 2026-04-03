from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from agents.base import StructuredAgent
from agents.models import Opportunity
from broker.models import MarketOrder, OrderSide
from data.bus import DataBus

logger = logging.getLogger(__name__)


class MomentumAgent(StructuredAgent):
    """Scans for stocks making N-day highs with above-average volume."""

    def __init__(self, config):
        super().__init__(config)
        self._last_signal: dict[str, datetime] = {}

    @property
    def description(self) -> str:
        return f"Momentum scanner: {self.parameters.get('lookback_days', 20)}-day high breakout"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        lookback = self.parameters.get("lookback_days", 20)
        vol_threshold = self.parameters.get("volume_threshold", 1.5)
        cooldown_hours = self.parameters.get("cooldown_hours", 24)

        symbols = data.get_universe(self.universe)
        opportunities: list[Opportunity] = []
        now = datetime.now(tz=timezone.utc)

        for symbol in symbols:
            try:
                last = self._last_signal.get(symbol.ticker)
                if last and (now - last) < timedelta(hours=cooldown_hours):
                    continue

                bars = await data.get_historical(symbol, "1d", "3mo")
                if len(bars) < lookback + 1:
                    continue

                recent = bars[-(lookback + 1):]
                current_close = float(recent[-1].close)
                prev_high = max(float(b.close) for b in recent[:-1])
                avg_volume = sum(b.volume for b in recent[:-1]) / lookback
                current_volume = recent[-1].volume

                if current_close <= prev_high:
                    continue
                if avg_volume == 0 or current_volume / avg_volume < vol_threshold:
                    continue

                volume_ratio = current_volume / avg_volume
                breakout_pct = (current_close - prev_high) / prev_high
                confidence = min(volume_ratio * breakout_pct * 10, 1.0)

                self._last_signal[symbol.ticker] = now

                opportunities.append(Opportunity(
                    id=str(uuid.uuid4()),
                    agent_name=self.name,
                    symbol=symbol,
                    signal="MOMENTUM_BREAKOUT",
                    confidence=confidence,
                    reasoning=(
                        f"{symbol.ticker} broke {lookback}-day high "
                        f"({current_close:.2f} > {prev_high:.2f}) "
                        f"with {volume_ratio:.1f}x avg volume"
                    ),
                    data={
                        "close": current_close,
                        "prev_high": prev_high,
                        "volume_ratio": volume_ratio,
                        "lookback_days": lookback,
                    },
                    timestamp=now,
                    suggested_trade=MarketOrder(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        quantity=Decimal("1"),
                        account_id="",
                    ),
                ))
            except Exception as e:
                logger.warning("Momentum scan failed for %s: %s", symbol.ticker, e)

        return opportunities
