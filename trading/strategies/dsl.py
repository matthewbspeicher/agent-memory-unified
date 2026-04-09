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


class ArbitrageDSLAgent(DSLAgent):
    """DSL agent extended with arbitrage-specific indicators.

    Adds arbitrage indicators:
    - spread_cents: Gap between Kalshi and Polymarket prices
    - match_score: Confidence that two tickers refer to the same event
    - volume_ratio: Ratio of volumes between venues (kalshi/poly)
    - implied_odds_diff: Difference in implied probabilities

    Example config:
    "rules": [
        {
            "conditions": [
                {"indicator": "spread_cents", "operator": ">=", "value": 5},
                {"indicator": "match_score", "operator": ">=", "value": 0.8}
            ],
            "action": "ARBITRAGE",
            "kalshi_ticker": "KALSHI_X",
            "poly_ticker": "POLY_X"
        }
    ]
    """

    @property
    def description(self) -> str:
        return "DSL agent with arbitrage-specific indicators for spread trading"

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

            # Handle standard indicators via parent
            if ind in ("rsi", "sma", "ema", "price"):
                actual_val = await self._get_standard_indicator(ind, symbol, data)
            # Handle arbitrage-specific indicators
            elif ind == "spread_cents":
                actual_val = await self._get_spread_cents(rule, data)
            elif ind == "match_score":
                actual_val = await self._get_match_score(rule, data)
            elif ind == "volume_ratio":
                actual_val = await self._get_volume_ratio(rule, data)
            elif ind == "implied_odds_diff":
                actual_val = await self._get_implied_odds_diff(rule, data)
            else:
                logger.warning("Unsupported arbitrage DSL indicator: %s", ind)
                return False

            # Apply operator
            if not self._compare(actual_val, op, target_val):
                return False

        return True

    async def _get_standard_indicator(
        self, indicator: str, symbol: Symbol, data: DataBus
    ) -> float:
        """Get value for standard (non-arbitrage) indicators."""
        if indicator == "rsi":
            return await data.get_rsi(symbol)
        elif indicator == "sma":
            return await data.get_sma(symbol)
        elif indicator == "ema":
            return await data.get_ema(symbol)
        elif indicator == "price":
            quote = await data.get_quote(symbol)
            return float(quote.last or 0.0)
        return 0.0

    async def _get_spread_cents(self, rule: dict[str, Any], data: DataBus) -> float:
        """Get spread in cents between Kalshi and Polymarket prices."""
        kalshi_ticker = rule.get("kalshi_ticker")
        poly_ticker = rule.get("poly_ticker")
        if not kalshi_ticker or not poly_ticker:
            return 0.0

        # Try to get spread from spread store via data bus
        try:
            kalshi_quote = await data.get_quote(Symbol(kalshi_ticker))
            poly_quote = await data.get_quote(Symbol(poly_ticker))
            kalshi_price = float(kalshi_quote.last or 0.0)
            poly_price = float(poly_quote.last or 0.0)
            # Convert to cents (prices are typically 0-1 for prediction markets)
            return abs(kalshi_price - poly_price) * 100
        except Exception:
            return 0.0

    async def _get_match_score(self, rule: dict[str, Any], data: DataBus) -> float:
        """Get match score between two tickers (from spread store if available)."""
        kalshi_ticker = rule.get("kalshi_ticker")
        poly_ticker = rule.get("poly_ticker")
        if not kalshi_ticker or not poly_ticker:
            return 0.0

        # Check if data bus provides match scores
        try:
            if hasattr(data, "get_match_score"):
                return await data.get_match_score(kalshi_ticker, poly_ticker)
        except Exception:
            pass
        return 0.0

    async def _get_volume_ratio(self, rule: dict[str, Any], data: DataBus) -> float:
        """Get volume ratio (kalshi/poly) for spread pair."""
        kalshi_ticker = rule.get("kalshi_ticker")
        poly_ticker = rule.get("poly_ticker")
        if not kalshi_ticker or not poly_ticker:
            return 0.0

        try:
            kalshi_quote = await data.get_quote(Symbol(kalshi_ticker))
            poly_quote = await data.get_quote(Symbol(poly_ticker))
            kalshi_vol = float(getattr(kalshi_quote, "volume", 0) or 0)
            poly_vol = float(getattr(poly_quote, "volume", 0) or 0)
            if poly_vol <= 0:
                return 0.0
            return kalshi_vol / poly_vol
        except Exception:
            return 0.0

    async def _get_implied_odds_diff(
        self, rule: dict[str, Any], data: DataBus
    ) -> float:
        """Get difference in implied probabilities between venues."""
        kalshi_ticker = rule.get("kalshi_ticker")
        poly_ticker = rule.get("poly_ticker")
        if not kalshi_ticker or not poly_ticker:
            return 0.0

        try:
            kalshi_quote = await data.get_quote(Symbol(kalshi_ticker))
            poly_quote = await data.get_quote(Symbol(poly_ticker))
            kalshi_prob = float(kalshi_quote.last or 0.0)
            poly_prob = float(poly_quote.last or 0.0)
            return abs(kalshi_prob - poly_prob) * 100  # Return as percentage points
        except Exception:
            return 0.0

    @staticmethod
    def _compare(actual: float, op: str, target: float) -> bool:
        """Compare actual vs target using operator."""
        if op == "<":
            return actual < target
        elif op == ">":
            return actual > target
        elif op == "<=":
            return actual <= target
        elif op == ">=":
            return actual >= target
        elif op == "==":
            return actual == target
        return False
