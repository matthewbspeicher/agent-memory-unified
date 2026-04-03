from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from agents.base import StructuredAgent
from agents.models import Opportunity
from broker.models import MarketOrder, OrderSide
from data.bus import DataBus

logger = logging.getLogger(__name__)


class MeanReversionAgent(StructuredAgent):
    """Fires when price crosses below the lower Bollinger Band with RSI confirmation."""

    def __init__(self, config):
        super().__init__(config)
        # Track per-symbol whether price was below band on last scan (cross detection)
        self._was_below_band: dict[str, bool] = {}

    @property
    def description(self) -> str:
        period = self.parameters.get("bb_period", 20)
        std = self.parameters.get("bb_std", 2.0)
        rsi_thresh = self.parameters.get("rsi_threshold", 35)
        return f"Mean reversion: BB({period},{std}) + RSI < {rsi_thresh}"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        bb_period = self.parameters.get("bb_period", 20)
        bb_std = self.parameters.get("bb_std", 2.0)
        rsi_threshold = self.parameters.get("rsi_threshold", 35)
        rsi_period = self.parameters.get("rsi_period", 14)

        symbols = data.get_universe(self.universe)
        opportunities: list[Opportunity] = []
        now = datetime.now(tz=timezone.utc)

        for symbol in symbols:
            try:
                quote = await data.get_quote(symbol)
                current_price = float(quote.last)

                bb = await data.get_bollinger(symbol, bb_period)
                lower_band = float(bb.lower)
                middle_band = float(bb.middle)

                rsi = await data.get_rsi(symbol, rsi_period)

                below_band = current_price < lower_band
                was_below = self._was_below_band.get(symbol.ticker, False)

                # Fire on the first bar where price crosses below the band (not while staying below)
                if below_band and not was_below and rsi < rsi_threshold:
                    band_width = float(bb.upper) - lower_band
                    distance_pct = (lower_band - current_price) / band_width if band_width > 0 else 0
                    rsi_score = (rsi_threshold - rsi) / rsi_threshold
                    confidence = min((distance_pct + rsi_score) / 2, 1.0)

                    opportunities.append(Opportunity(
                        id=str(uuid.uuid4()),
                        agent_name=self.name,
                        symbol=symbol,
                        signal="MEAN_REVERSION_OVERSOLD",
                        confidence=confidence,
                        reasoning=(
                            f"{symbol.ticker} crossed below lower BB ({current_price:.2f} < {lower_band:.2f}), "
                            f"RSI({rsi_period}) = {rsi:.1f} (< {rsi_threshold})"
                        ),
                        data={
                            "price": current_price,
                            "lower_band": lower_band,
                            "middle_band": middle_band,
                            "rsi": rsi,
                            "rsi_threshold": rsi_threshold,
                        },
                        timestamp=now,
                        suggested_trade=MarketOrder(
                            symbol=symbol,
                            side=OrderSide.BUY,
                            quantity=Decimal("1"),
                            account_id="",
                        ),
                    ))

                self._was_below_band[symbol.ticker] = below_band

            except Exception as e:
                logger.warning("MeanReversion scan failed for %s: %s", symbol.ticker, e)

        return opportunities
