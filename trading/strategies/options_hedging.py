from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from agents.base import StructuredAgent
from agents.models import Opportunity
from broker.models import AssetType
from broker.options import build_iron_condor, build_iron_butterfly, build_protective_put, build_collar
from data.bus import DataBus

logger = logging.getLogger(__name__)


def find_closest_strike(strikes: list[Decimal], target: Decimal) -> Decimal:
    if not strikes:
        return Decimal("0")
    return min(strikes, key=lambda x: abs(x - target))


class OptionsHedgingAgent(StructuredAgent):
    @property
    def description(self) -> str:
        s = self.parameters.get("strategy", "iron_condor")
        return f"Hedging agent recommending {s} for open long equity positions"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        opportunities: list[Opportunity] = []
        
        # This agent only makes sense if we are scanning PORTFOLIO or EVERYTHING
        if self.universe and "PORTFOLIO" not in self.universe and self.universe != "ALL":
            return opportunities

        try:
            positions = await data.get_positions()
        except Exception as e:
            logger.warning("Options hedging agent failed to get positions: %s", e)
            return opportunities

        strategy_type = self.parameters.get("strategy", "iron_condor")
        target_delta = Decimal(str(self.parameters.get("target_delta", 0.16)))
        dte_min = self.parameters.get("dte_min", 30)
        dte_max = self.parameters.get("dte_max", 45)

        for pos in positions:
            if pos.symbol.asset_type != AssetType.STOCK:
                continue
                
            qty = pos.quantity
            if qty <= 0:
                continue # Only hedge long positions
                
            try:
                quote = await data.get_quote(pos.symbol)
            except Exception:
                continue

            current_price = quote.last if quote.last else (quote.ask or quote.bid)
            if not current_price:
                continue
                
            try:
                chain = await data.get_options_chain(pos.symbol)
            except Exception as e:
                logger.debug("Could not fetch options chain for %s: %s", pos.symbol.ticker, e)
                continue
            
            if not chain.expirations or not chain.strikes:
                continue
                
            # Pick expiration between dte_min and dte_max
            now = datetime.now(timezone.utc).date()
            valid_expiries = [
                d for d in chain.expirations 
                if dte_min <= (d - now).days <= dte_max
            ]
            
            if not valid_expiries:
                continue
                
            expiry = valid_expiries[0] # closest to dte_min
            strikes = sorted(chain.strikes)
            
            suggested_trade = None
            reasoning = ""
            conf = 0.8  # Static confidence for now; can be enhanced with IV rank checks
            
            if strategy_type == "collar":
                put_strike = find_closest_strike(strikes, current_price * Decimal("0.90"))
                call_strike = find_closest_strike(strikes, current_price * Decimal("1.10"))
                suggested_trade = build_collar(
                    "PAPER", pos.symbol, Decimal("1"), expiry, put_strike, call_strike
                )
                reasoning = (
                    f"Suggesting Collar hedge for {pos.symbol.ticker} long position. "
                    f"Current: ${current_price:.2f}. Expiry: {expiry}. "
                    f"Buy {put_strike}P, Sell {call_strike}C."
                )
            
            elif strategy_type == "iron_condor":
                # Simulated roughly based on distance (simplified target_delta proxy)
                put_long = find_closest_strike(strikes, current_price * Decimal("0.85"))
                put_short = find_closest_strike(strikes, current_price * Decimal("0.90"))
                call_short = find_closest_strike(strikes, current_price * Decimal("1.10"))
                call_long = find_closest_strike(strikes, current_price * Decimal("1.15"))
                
                suggested_trade = build_iron_condor(
                    "PAPER", pos.symbol, Decimal("1"), expiry, 
                    put_short, put_long, call_short, call_long
                )
                reasoning = (
                    f"Suggesting Iron Condor for {pos.symbol.ticker} at ${current_price:.2f}. "
                    f"Short [{put_short}P, {call_short}C], Long [{put_long}P, {call_long}C]"
                )

            elif strategy_type == "iron_butterfly":
                atm = find_closest_strike(strikes, current_price)
                put_long = find_closest_strike(strikes, current_price * Decimal("0.85"))
                call_long = find_closest_strike(strikes, current_price * Decimal("1.15"))
                suggested_trade = build_iron_butterfly(
                    "PAPER", pos.symbol, Decimal("1"), expiry, 
                    atm, put_long, call_long
                )
                reasoning = (
                    f"Suggesting Iron Butterfly for {pos.symbol.ticker} at ${current_price:.2f}. "
                    f"Short ATM [{atm}P, {atm}C], Long Wings [{put_long}P, {call_long}C]"
                )

            elif strategy_type == "protective_put":
                put_strike = find_closest_strike(strikes, current_price * Decimal("0.95"))
                suggested_trade = build_protective_put(
                    "PAPER", pos.symbol, Decimal("1"), expiry, put_strike
                )
                reasoning = f"Suggesting Protective Put for {pos.symbol.ticker} at {put_strike} strike."

            if suggested_trade:
                opp = Opportunity(
                    id=str(uuid.uuid4()),
                    agent_name=self.name,
                    symbol=pos.symbol,
                    signal=f"HEDGE_{strategy_type.upper()}",
                    confidence=conf,
                    reasoning=reasoning,
                    data={
                        "current_price": float(current_price),
                        "expiry": str(expiry),
                        "strategy": strategy_type
                    },
                    timestamp=datetime.now(timezone.utc),
                    suggested_trade=suggested_trade
                )
                opportunities.append(opp)
                
        return opportunities
