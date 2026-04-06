"""
KalshiTimeDecayAgent — Time-decay (theta) seller for near-expiry Kalshi markets.

Targets markets that are:
- Close to expiry (within max_days_to_close)
- Trading at a low YES price (< max_price_cents)
- Sufficiently liquid (volume_24h >= min_volume)

Sells YES (equivalently, buys NO) to capture the remaining cents as the
probability converges to 0.

agents.yaml example:
  - name: kalshi_theta
    strategy: kalshi_time_decay
    schedule: cron
    cron: "0 9 * * *"   # run once per day at open
    action_level: suggest_trade
    parameters:
      max_days_to_close: 3
      max_price_cents: 8
      min_volume: 300
      categories: ["economics", "politics"]
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from agents.base import StructuredAgent
from agents.models import Opportunity, OpportunityStatus
from broker.models import LimitOrder, OrderSide, TIF

if TYPE_CHECKING:
    from data.bus import DataBus

logger = logging.getLogger(__name__)


class KalshiTimeDecayAgent(StructuredAgent):
    description = (
        "Sells YES contracts on near-expiry Kalshi markets where the outcome "
        "is implausible, capturing the remaining time value as probability "
        "decays to zero."
    )

    async def scan(self, data: DataBus) -> list[Opportunity]:
        params = self.parameters
        max_days: float = float(params.get("max_days_to_close", 3))
        max_price: int = int(params.get("max_price_cents", 8))
        min_volume: int = int(params.get("min_volume", 200))
        categories: list[str] = params.get("categories", [])

        kalshi_source = getattr(data, "_kalshi_source", None)
        if kalshi_source is None:
            logger.warning("%s: no KalshiDataSource on DataBus — skipping", self.name)
            return []

        now = datetime.now(timezone.utc)
        expiry_cutoff = now + timedelta(days=max_days)

        opportunities: list[Opportunity] = []
        fetch_cats = categories if categories else [None]  # None = all categories

        for cat in fetch_cats:
            markets = await kalshi_source.get_markets(category=cat)
            for contract in markets:
                # Must expire soon
                if contract.close_time > expiry_cutoff:
                    continue
                # Must have a low YES price (we want to sell YES) OR high YES price (we want to sell NO)
                yes_price = contract.yes_bid
                if yes_price is None:
                    continue

                if yes_price <= max_price:
                    action = OrderSide.SELL
                    target_cents = yes_price
                    direction = "SELL_YES"
                    100 - yes_price
                    reason = f"Selling YES to capture {yes_price}¢ time value."
                elif yes_price >= (100 - max_price):
                    no_price = 100 - yes_price
                    action = OrderSide.BUY
                    target_cents = no_price
                    direction = "SELL_NO"
                    reason = (
                        f"Selling NO (Buying NO) to capture {no_price}¢ time value."
                    )
                else:
                    continue

                # Must be liquid enough
                if contract.volume_24h < min_volume:
                    continue
                # Skip already resolved markets
                if contract.result is not None:
                    continue

                days_left = (contract.close_time - now).total_seconds() / 86400
                symbol = contract.as_symbol

                # Target limit price
                limit_price = Decimal(str(target_cents)) / Decimal("100")

                suggested = LimitOrder(
                    symbol=symbol,
                    side=action,
                    quantity=Decimal("20"),
                    account_id="KALSHI",
                    limit_price=limit_price,
                    time_in_force=TIF.GTC,
                )

                # Confidence scales with: extreme price & very near expiry
                price_extremity = (
                    (max_price - yes_price) / max_price
                    if direction == "SELL_YES"
                    else (yes_price - (100 - max_price)) / max_price
                )
                price_extremity = max(0.0, price_extremity)
                confidence = round(
                    (0.2 + 0.8 * price_extremity) * (1 - days_left / max_days) * 0.85, 3
                )

                opportunities.append(
                    Opportunity(
                        id=str(uuid.uuid4()),
                        agent_name=self.name,
                        symbol=symbol,
                        signal=direction,
                        confidence=confidence,
                        reasoning=(
                            f"Near-certain market expiring in {days_left:.1f}d at {yes_price}¢. "
                            f"{reason}\nQ: {contract.title}"
                        ),
                        data={
                            "category": contract.category,
                            "yes_price_cents": yes_price,
                            "days_to_close": round(days_left, 2),
                            "volume_24h": contract.volume_24h,
                            "close_time": contract.close_time.isoformat(),
                        },
                        timestamp=datetime.now(timezone.utc),
                        suggested_trade=suggested,
                        status=OpportunityStatus.PENDING,
                    )
                )

        # Sort by highest confidence (lowest price, nearest expiry)
        opportunities.sort(key=lambda o: o.confidence, reverse=True)
        return opportunities[:20]  # cap at 20 per scan
