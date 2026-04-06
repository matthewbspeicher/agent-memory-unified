"""
Polymarket Time Decay (Theta) Agent.

Scans for near-expiry Polymarket markets with extremely low (or high) probabilities.
Since the market outcome is virtually certain, this agent attempts to extract the
remaining cents (theta decay) by selling the prevailing highly-likely side.
It is symmetric: sells YES on <5c markets, sells NO on >95c markets.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from agents.base import Agent
from agents.models import AgentConfig, Opportunity
from broker.models import LimitOrder, OrderSide

logger = logging.getLogger(__name__)


class PolymarketTimeDecayAgent(Agent):
    description = "Theta decay capture on near-expiry highly certain Polymarket events."

    def __init__(self, config: AgentConfig, **kwargs):
        super().__init__(config, **kwargs)

        params = config.parameters or {}
        self.max_days = params.get("max_days_to_close", 3)
        self.max_price = params.get("max_price_cents", 5)
        self.min_volume = params.get("min_volume", 500)
        self.max_markets = params.get("max_markets_per_scan", 50)

    async def scan(self, data) -> list[Opportunity]:
        app_state = getattr(self.config, "_app_state", None)
        if app_state and "polymarket" not in app_state.brokers:
            return []

        ds = getattr(data, "_polymarket_source", None)
        if not ds:
            return []

        now = datetime.now(timezone.utc)
        opportunities = []

        markets = await ds.get_markets(closed=False, limit=self.max_markets)
        # Using a list comprehension for filtering where close_time is valid
        valid_markets = []
        for mkt in markets:
            if not mkt.close_time or mkt.volume_24h < self.min_volume:
                continue
            try:
                ct = datetime.fromisoformat(mkt.close_time.replace("Z", "+00:00"))
                days_to_close = (ct - now).total_seconds() / 86400.0
                if 0 < days_to_close <= self.max_days:
                    # Stash it so we don't recalculate
                    mkt._days_to_close = days_to_close
                    valid_markets.append(mkt)
            except ValueError:
                pass

        for mkt in valid_markets[: self.max_markets]:
            yes_price = mkt.yes_bid
            if yes_price <= self.max_price:
                # Outcome is almost certainly NO. Sell YES (bet NO) at target price
                # e.g. market YES is 3c. We sell YES at 3c.
                target_prob = yes_price / 100.0
                sym = mkt.as_symbol

                opportunities.append(
                    Opportunity(
                        id=f"poly_theta_NO_{mkt.ticker}_{now.timestamp()}",
                        agent_name=self.name,
                        symbol=sym,
                        signal="SELL_YES",
                        confidence=0.9,
                        reasoning=f"Selling YES due to <5c decay.\nQ:{mkt.title}",
                        broker_id="polymarket",
                        suggested_trade=LimitOrder(
                            symbol=sym,
                            side=OrderSide.SELL,
                            quantity=20,
                            account_id="POLY",
                            limit_price=target_prob,
                        ),
                        data={
                            "side": "YES_TOO_LOW",
                            "price": yes_price,
                            "days_to_close": mkt._days_to_close,
                        },
                        timestamp=now,
                    )
                )
            elif yes_price >= (100 - self.max_price):
                target_prob = yes_price / 100.0
                sym = mkt.as_symbol

                opportunities.append(
                    Opportunity(
                        id=f"poly_theta_YES_{mkt.ticker}_{now.timestamp()}",
                        agent_name=self.name,
                        symbol=sym,
                        signal="SELL_NO",
                        confidence=0.9,
                        reasoning=f"Selling NO due to >95c decay.\nQ:{mkt.title}",
                        broker_id="polymarket",
                        suggested_trade=LimitOrder(
                            symbol=sym,
                            side=OrderSide.BUY,
                            quantity=20,
                            account_id="POLY",
                            limit_price=target_prob,
                        ),
                        data={
                            "side": "YES_TOO_HIGH",
                            "price": yes_price,
                            "days_to_close": mkt._days_to_close,
                        },
                        timestamp=now,
                    )
                )

        return opportunities
