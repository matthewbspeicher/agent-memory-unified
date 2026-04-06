import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from agents.base import StructuredAgent
from agents.models import Opportunity
from broker.models import OrderSide, Symbol, MarketOrder
from data.bus import DataBus

logger = logging.getLogger(__name__)


class DSLAgent(StructuredAgent):
    """
    Executes declarative strategies defined in YAML/JSON parameters.
    Example config parameters:
    "rules": [
        {
            "conditions": [
                {"indicator": "rsi", "operator": "<", "value": 30}
            ],
            "action": "BUY",
            "quantity": 10
        }
    ]
    """

    @property
    def description(self) -> str:
        return "Executes declarative YAML DSL strategies"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        opportunities = []
        rules = self.parameters.get("rules", [])

        # Handle string or list of symbols
        univ_names = (
            self.universe if isinstance(self.universe, list) else [self.universe]
        )

        symbols = []
        for name in univ_names:
            if name:  # Avoid passing empty string
                try:
                    symbols.extend(data.get_universe(name))
                except Exception:
                    # In tests we might not have a full universe
                    symbols.append(Symbol(name))

        if not symbols and univ_names:
            symbols = [Symbol(n) for n in univ_names]

        for symbol in symbols:
            for rule in rules:
                matched = await self._evaluate_rule(rule, symbol, data)
                if matched:
                    action_str = rule.get("action", "BUY").upper()
                    side = OrderSide.BUY if action_str == "BUY" else OrderSide.SELL
                    qty = Decimal(str(rule.get("quantity", 10)))

                    # Need a current timestamp
                    now = getattr(data, "current_time", None) or datetime.now(
                        timezone.utc
                    )

                    opp = Opportunity(
                        id=f"{self.name}_{symbol.ticker}_{action_str}_{int(now.timestamp())}",
                        agent_name=self.name,
                        symbol=symbol,
                        signal="DSL_MATCH",
                        confidence=self.parameters.get("confidence_threshold", 0.8),
                        reasoning=f"Matched DSL rule: {rule}",
                        data={"rule": rule},
                        timestamp=now,
                        suggested_trade=MarketOrder(
                            symbol=symbol, side=side, quantity=qty, account_id=""
                        ),
                    )
                    opportunities.append(opp)

        return opportunities

    async def _evaluate_rule(
        self, rule: dict[str, Any], symbol: Symbol, data: DataBus
    ) -> bool:
        conditions = rule.get("conditions", [])
        if not conditions:
            return False

        for cond in conditions:
            ind = str(cond.get("indicator")).lower()
            op = cond.get("operator")
            target_val = float(cond.get("value", 0.0))

            actual_val = 0.0
            if ind == "rsi":
                actual_val = await data.get_rsi(symbol)
            elif ind == "sma":
                actual_val = await data.get_sma(symbol)
            elif ind == "ema":
                actual_val = await data.get_ema(symbol)
            elif ind == "price":
                quote = await data.get_quote(symbol)
                actual_val = float(quote.last or 0.0)
            else:
                logger.warning("Unsupported DSL indicator: %s", ind)
                return False

            if op == "<":
                if not (actual_val < target_val):
                    return False
            elif op == ">":
                if not (actual_val > target_val):
                    return False
            elif op == "<=":
                if not (actual_val <= target_val):
                    return False
            elif op == ">=":
                if not (actual_val >= target_val):
                    return False
            elif op == "==":
                if not (actual_val == target_val):
                    return False
            else:
                logger.warning("Unsupported DSL operator: %s", op)
                return False

        return True
