from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from agents.base import StructuredAgent
from agents.models import Opportunity
from broker.models import MarketOrder, OrderSide
from data.bus import DataBus
from data.indicators import compute_macd, compute_rsi

logger = logging.getLogger(__name__)


class MultiFactorAgent(StructuredAgent):
    """Composite scoring: RSI + MACD + volume. Emits BUY-only signals (Phase 1)."""

    def __init__(self, config):
        super().__init__(config)
        # Cross-detection: fire only when composite crosses above threshold
        self._was_above: dict[str, bool] = {}

    @property
    def description(self) -> str:
        threshold = self.parameters.get("composite_threshold", 0.6)
        return f"Multi-factor scanner: RSI+MACD+volume composite > {threshold}"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        threshold = self.parameters.get("composite_threshold", 0.6)
        rsi_weight = self.parameters.get("rsi_weight", 0.4)
        macd_weight = self.parameters.get("macd_weight", 0.3)
        volume_weight = self.parameters.get("volume_weight", 0.3)
        lookback = self.parameters.get("lookback_days", 20)
        rsi_period = self.parameters.get("rsi_period", 14)

        symbols = data.get_universe(self.universe)
        opportunities: list[Opportunity] = []
        now = datetime.now(tz=timezone.utc)

        for symbol in symbols:
            try:
                bars = await data.get_historical(symbol, "1d", "3mo")

                required_bars = max(lookback + 1, rsi_period + 1, 35)
                if len(bars) < required_bars:
                    continue

                rsi = compute_rsi(bars, rsi_period)
                macd_result = compute_macd(bars)

                recent = bars[-(lookback + 1):]
                current_bar = recent[-1]
                lookback_bars = recent[:-1]

                # RSI factor: positive when oversold (RSI < 50), negative when overbought
                rsi_factor = (50.0 - rsi) / 50.0

                # MACD factor: direction + magnitude normalized by recent price range
                highs = [float(b.high) for b in lookback_bars]
                lows = [float(b.low) for b in lookback_bars]
                recent_range = max(highs) - min(lows) if highs and lows else 1.0
                if recent_range == 0:
                    recent_range = 1.0

                macd_diff = float(macd_result.macd_line) - float(macd_result.signal_line)
                sign = 1.0 if macd_diff > 0 else (-1.0 if macd_diff < 0 else 0.0)
                macd_factor = sign * min(abs(macd_diff) / recent_range, 1.0)

                # Volume factor: excess volume above average (capped at 1.0)
                avg_volume = sum(b.volume for b in lookback_bars) / len(lookback_bars) if lookback_bars else 1
                current_volume = current_bar.volume
                volume_factor = min((current_volume / avg_volume - 1.0), 1.0) if avg_volume > 0 else 0.0

                composite = (
                    rsi_weight * rsi_factor
                    + macd_weight * macd_factor
                    + volume_weight * volume_factor
                )

                above_threshold = composite > threshold
                was_above = self._was_above.get(symbol.ticker, False)

                # Fire only on the crossing event (not while remaining above)
                if above_threshold and not was_above:
                    opportunities.append(Opportunity(
                        id=str(uuid.uuid4()),
                        agent_name=self.name,
                        symbol=symbol,
                        signal="MULTI_FACTOR_BUY",
                        confidence=min(composite, 1.0),
                        reasoning=(
                            f"{symbol.ticker} composite score {composite:.2f} > {threshold} "
                            f"(RSI factor={rsi_factor:.2f}, MACD factor={macd_factor:.2f}, "
                            f"volume factor={volume_factor:.2f})"
                        ),
                        data={
                            "composite": composite,
                            "rsi_factor": rsi_factor,
                            "macd_factor": macd_factor,
                            "volume_factor": volume_factor,
                            "rsi": rsi,
                        },
                        timestamp=now,
                        suggested_trade=MarketOrder(
                            symbol=symbol,
                            side=OrderSide.BUY,
                            quantity=Decimal("1"),
                            account_id="",
                        ),
                    ))

                self._was_above[symbol.ticker] = above_threshold

            except Exception as e:
                logger.warning("MultiFactorAgent scan failed for %s: %s", symbol.ticker, e)

        return opportunities
