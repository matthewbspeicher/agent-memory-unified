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


class RSIAgent(StructuredAgent):
    # Gemini design §2.1: Parameter schema for Hermes composition
    PARAMETER_SCHEMA = {
        "period": {"type": "int", "min": 5, "max": 50, "default": 14},
        "oversold": {"type": "int", "min": 10, "max": 40, "default": 30},
        "overbought": {"type": "int", "min": 60, "max": 90, "default": 70},
    }

    @property
    def description(self) -> str:
        return f"RSI scanner: oversold<{self.parameters.get('oversold', 30)}, overbought>{self.parameters.get('overbought', 70)}"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        period = self.parameters.get("period", 14)
        oversold = self.parameters.get("oversold", 30)
        overbought = self.parameters.get("overbought", 70)

        symbols = data.get_universe(self.universe)
        opportunities: list[Opportunity] = []

        for symbol in symbols:
            try:
                rsi = await data.get_rsi(symbol, period)
            except Exception as e:
                logger.warning("RSI scan failed for %s: %s", symbol.ticker, e)
                continue

            if rsi <= oversold:
                confidence = (oversold - rsi) / oversold
                opportunities.append(
                    Opportunity(
                        id=str(uuid.uuid4()),
                        agent_name=self.name,
                        symbol=symbol,
                        signal="RSI_OVERSOLD",
                        confidence=min(confidence, 1.0),
                        reasoning=f"{symbol.ticker} RSI({period}) = {rsi:.1f}, below oversold threshold {oversold}",
                        data={"rsi": rsi, "period": period, "threshold": oversold},
                        timestamp=datetime.now(timezone.utc),
                        suggested_trade=MarketOrder(
                            symbol=symbol,
                            side=OrderSide.BUY,
                            quantity=Decimal("1"),
                            account_id="",
                        ),
                    )
                )
            elif rsi >= overbought:
                confidence = (rsi - overbought) / (100 - overbought)
                opportunities.append(
                    Opportunity(
                        id=str(uuid.uuid4()),
                        agent_name=self.name,
                        symbol=symbol,
                        signal="RSI_OVERBOUGHT",
                        confidence=min(confidence, 1.0),
                        reasoning=f"{symbol.ticker} RSI({period}) = {rsi:.1f}, above overbought threshold {overbought}",
                        data={"rsi": rsi, "period": period, "threshold": overbought},
                        timestamp=datetime.now(timezone.utc),
                        # No suggested_trade for overbought — notify only in Phase 1
                    )
                )

        return opportunities
