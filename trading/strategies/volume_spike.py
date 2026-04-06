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


class VolumeSpikeAgent(StructuredAgent):
    @property
    def description(self) -> str:
        return f"Volume spike detector: {self.parameters.get('volume_threshold', 2.0)}x average"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        threshold = self.parameters.get("volume_threshold", 2.0)
        symbols = data.get_universe(self.universe)
        opportunities: list[Opportunity] = []

        for symbol in symbols:
            try:
                bars = await data.get_historical(symbol, "1d", "1mo")
                quote = await data.get_quote(symbol)
            except Exception as e:
                logger.warning("Volume scan failed for %s: %s", symbol.ticker, e)
                continue

            if not bars or quote.volume == 0:
                continue

            avg_volume = sum(b.volume for b in bars) / len(bars)
            if avg_volume == 0:
                continue

            ratio = quote.volume / avg_volume
            if ratio >= threshold:
                # Price direction confirmation: bullish only when last bar closes above open
                most_recent_bar = bars[-1]
                is_bullish = most_recent_bar.close > most_recent_bar.open
                suggested_trade = (
                    MarketOrder(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        quantity=Decimal("1"),
                        account_id="",
                    )
                    if is_bullish
                    else None
                )
                opportunities.append(
                    Opportunity(
                        id=str(uuid.uuid4()),
                        agent_name=self.name,
                        symbol=symbol,
                        signal="VOLUME_SPIKE",
                        confidence=min((ratio - threshold) / threshold + 0.5, 1.0),
                        reasoning=f"{symbol.ticker} volume {quote.volume:,} is {ratio:.1f}x the {len(bars)}-day average {avg_volume:,.0f}",
                        data={
                            "volume_ratio": ratio,
                            "current_volume": quote.volume,
                            "avg_volume": avg_volume,
                        },
                        timestamp=datetime.now(timezone.utc),
                        suggested_trade=suggested_trade,
                    )
                )

        return opportunities
