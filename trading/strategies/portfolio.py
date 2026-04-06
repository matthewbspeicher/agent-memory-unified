import json
import logging
from datetime import datetime, timezone

from agents.base import StructuredAgent
from agents.models import Opportunity
from broker.models import OrderSide, MarketOrder
from data.bus import DataBus

logger = logging.getLogger(__name__)

class PositionMonitorAgent(StructuredAgent):
    @property
    def description(self) -> str:
        return "Monitors for stale or underwater positions"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        stale_days = self.parameters.get("stale_days", 30)
        underwater_pct = self.parameters.get("underwater_pct", -10.0)
        
        positions = await data.get_positions()
        opportunities = []

        # Find recent trades to estimate holding periods
        trades = await data.get_recent_trades(limit=500)
        last_trade_dates = {}
        for t in trades:
            order_res = json.loads(t["order_result"]) if isinstance(t["order_result"], str) else t["order_result"]
            sym = order_res.get("symbol", {}).get("ticker")
            if sym and sym not in last_trade_dates:
                created_str = t.get("created_at")
                if created_str:
                    try:
                        last_trade_dates[sym] = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                    except ValueError:
                        pass # Ignore malformed dates

        now = datetime.now(timezone.utc)

        for pos in positions:
            market_val = float(pos.market_value)
            if market_val == 0:
                continue
            
            pnl = float(pos.unrealized_pnl)
            cost_basis = market_val - pnl
            pct_return = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0

            reasons = []
            if pct_return <= underwater_pct:
                reasons.append(f"Position is underwater ({pct_return:.1f}% return)")

            # Check staleness based on last trade in db
            last_date = last_trade_dates.get(pos.symbol.ticker)
            if last_date:
                # Ensure last_date is timezone aware
                if last_date.tzinfo is None:
                    last_date = last_date.replace(tzinfo=timezone.utc)
                days_held = (now - last_date).days
                if days_held >= stale_days:
                    reasons.append(f"Position is stale (held {days_held} days)")

            if reasons:
                opp = Opportunity(
                    id=f"{self.name}_{pos.symbol.ticker}_{int(now.timestamp())}",
                    agent_name=self.name,
                    symbol=pos.symbol,
                    signal="review_position",
                    confidence=0.8,
                    reasoning="; ".join(reasons),
                    data={"pnl_pct": pct_return, "stale": bool(last_date and days_held >= stale_days)},
                    timestamp=now,
                )
                opportunities.append(opp)
        
        return opportunities


class TaxLossHarvestingAgent(StructuredAgent):
    @property
    def description(self) -> str:
        return "Scans for tax-loss harvesting opportunities avoiding wash sales"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        min_loss_amount = float(self.parameters.get("min_loss_amount", 500.0))
        wash_sale_days = int(self.parameters.get("wash_sale_days", 30))
        
        positions = await data.get_positions()
        opportunities = []

        trades = await data.get_recent_trades(limit=500)
        recent_trade_dates = {}
        for t in trades:
            order_res = json.loads(t["order_result"]) if isinstance(t["order_result"], str) else t["order_result"]
            sym = order_res.get("symbol", {}).get("ticker")
            if sym:
                created_str = t.get("created_at")
                if created_str:
                    try:
                        dt = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if sym not in recent_trade_dates or dt > recent_trade_dates[sym]:
                            recent_trade_dates[sym] = dt
                    except ValueError:
                        pass

        now = datetime.now(timezone.utc)

        for pos in positions:
            pnl = float(pos.unrealized_pnl)
            if pnl > -min_loss_amount:
                continue

            last_date = recent_trade_dates.get(pos.symbol.ticker)
            if last_date and (now - last_date).days <= wash_sale_days:
                logger.info("Skipping tax loss harvest for %s due to wash sale rule (traded %d days ago)", 
                          pos.symbol.ticker, (now - last_date).days)
                continue

            # Suggest market sell to realize loss. Note: for Options we'd need more logic, 
            # assuming stock for now. Router will auto-fill account_id if missing.
            suggested_trade = MarketOrder(
                symbol=pos.symbol,
                side=OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY,
                quantity=abs(pos.quantity),
                account_id=""
            )

            opp = Opportunity(
                id=f"{self.name}_{pos.symbol.ticker}_{int(now.timestamp())}",
                agent_name=self.name,
                symbol=pos.symbol,
                signal="tax_loss_harvest",
                confidence=0.9,
                reasoning=f"Position has ${-pnl:.2f} unrealized loss. No trades in last {wash_sale_days} days.",
                data={"unrealized_loss": -pnl, "wash_sale_clear": True},
                timestamp=now,
                suggested_trade=suggested_trade
            )
            opportunities.append(opp)
        
        return opportunities
