from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from rules.models import Rule, RuleResult, RuleSet, RuleSetResult

logger = logging.getLogger(__name__)


class RulesEngine:
    def __init__(self):
        self._conditions = {
            "price_above": self._eval_price_above,
            "price_below": self._eval_price_below,
            "rsi_above": self._eval_rsi_above,
            "rsi_below": self._eval_rsi_below,
            "ema_above": self._eval_ema_above,
            "ema_below": self._eval_ema_below,
            "vwap_above": self._eval_vwap_above,
            "vwap_below": self._eval_vwap_below,
            "distance_within_pct": self._eval_distance_within_pct,
            "volatility_above": self._eval_volatility_above,
            "bias_bullish": self._eval_bias_bullish,
            "bias_bearish": self._eval_bias_bearish,
        }

    def validate(
        self,
        rule_set: RuleSet,
        market_data: dict[str, Any],
    ) -> RuleSetResult:
        results = []

        for rule in rule_set.entry_rules:
            if not rule.enabled:
                continue
            result = self._evaluate_rule(rule, market_data)
            results.append(result)
            if not result.passed:
                logger.info(
                    "Rule failed: %s (actual: %s, required: %s)",
                    rule.name,
                    result.actual,
                    result.required,
                )

        for rule in rule_set.risk_rules:
            if not rule.enabled:
                continue
            result = self._evaluate_rule(rule, market_data)
            results.append(result)
            if not result.passed:
                logger.warning("Risk rule failed: %s", rule.name)

        all_pass = all(r.passed for r in results)
        return RuleSetResult(rule_set=rule_set, results=results, all_pass=all_pass)

    def _evaluate_rule(self, rule: Rule, market_data: dict[str, Any]) -> RuleResult:
        evaluator = self._conditions.get(rule.condition)
        if not evaluator:
            return RuleResult(
                rule=rule,
                passed=False,
                actual="unknown condition",
                required=f"condition={rule.condition}",
            )
        return evaluator(rule, market_data)

    def _eval_price_above(self, rule: Rule, data: dict) -> RuleResult:
        price = data.get("price", Decimal("0"))
        threshold = Decimal(str(rule.threshold or 0))
        return RuleResult(
            rule=rule,
            passed=price > threshold,
            actual=str(price),
            required=f"> {threshold}",
        )

    def _eval_price_below(self, rule: Rule, data: dict) -> RuleResult:
        price = data.get("price", Decimal("0"))
        threshold = Decimal(str(rule.threshold or 0))
        return RuleResult(
            rule=rule,
            passed=price < threshold,
            actual=str(price),
            required=f"< {threshold}",
        )

    def _eval_rsi_above(self, rule: Rule, data: dict) -> RuleResult:
        rsi = data.get("rsi", 0)
        threshold = rule.threshold or 70
        return RuleResult(
            rule=rule,
            passed=rsi > threshold,
            actual=f"{rsi:.2f}",
            required=f"> {threshold}",
        )

    def _eval_rsi_below(self, rule: Rule, data: dict) -> RuleResult:
        rsi = data.get("rsi", 0)
        threshold = rule.threshold or 30
        return RuleResult(
            rule=rule,
            passed=rsi < threshold,
            actual=f"{rsi:.2f}",
            required=f"< {threshold}",
        )

    def _eval_ema_above(self, rule: Rule, data: dict) -> RuleResult:
        price = data.get("price", Decimal("0"))
        ema = (
            data.get(f"ema_{rule.threshold}", Decimal("0"))
            if rule.threshold
            else data.get("ema", Decimal("0"))
        )
        return RuleResult(
            rule=rule,
            passed=price > ema,
            actual=f"{price} vs EMA{int(rule.threshold or 8)}",
            required="> ema",
        )

    def _eval_ema_below(self, rule: Rule, data: dict) -> RuleResult:
        price = data.get("price", Decimal("0"))
        ema = (
            data.get(f"ema_{rule.threshold}", Decimal("0"))
            if rule.threshold
            else data.get("ema", Decimal("0"))
        )
        return RuleResult(
            rule=rule,
            passed=price < ema,
            actual=f"{price} vs EMA{int(rule.threshold or 8)}",
            required="< ema",
        )

    def _eval_vwap_above(self, rule: Rule, data: dict) -> RuleResult:
        price = data.get("price", Decimal("0"))
        vwap = data.get("vwap", Decimal("0"))
        if not vwap:
            return RuleResult(
                rule=rule, passed=False, actual="N/A", required="vwap available"
            )
        return RuleResult(
            rule=rule,
            passed=price > vwap,
            actual=f"{price} vs {vwap}",
            required="> vwap",
        )

    def _eval_vwap_below(self, rule: Rule, data: dict) -> RuleResult:
        price = data.get("price", Decimal("0"))
        vwap = data.get("vwap", Decimal("0"))
        if not vwap:
            return RuleResult(
                rule=rule, passed=False, actual="N/A", required="vwap available"
            )
        return RuleResult(
            rule=rule,
            passed=price < vwap,
            actual=f"{price} vs {vwap}",
            required="< vwap",
        )

    def _eval_distance_within_pct(self, rule: Rule, data: dict) -> RuleResult:
        price = data.get("price", Decimal("0"))
        vwap = data.get("vwap", Decimal("0"))
        if not vwap:
            return RuleResult(
                rule=rule, passed=False, actual="N/A", required="vwap available"
            )
        pct = abs((price - vwap) / vwap) * 100
        threshold = rule.threshold or 1.5
        return RuleResult(
            rule=rule,
            passed=float(pct) < threshold,
            actual=f"{pct:.2f}%",
            required=f"< {threshold}%",
        )

    def _eval_bias_bullish(self, rule: Rule, data: dict) -> RuleResult:
        price = data.get("price", Decimal("0"))
        vwap = data.get("vwap", Decimal("0"))
        ema = data.get("ema", Decimal("0"))
        bullish = price > vwap and price > ema
        return RuleResult(
            rule=rule,
            passed=bullish,
            actual="bullish" if bullish else "neutral",
            required="bullish",
        )

    def _eval_bias_bearish(self, rule: Rule, data: dict) -> RuleResult:
        price = data.get("price", Decimal("0"))
        vwap = data.get("vwap", Decimal("0"))
        ema = data.get("ema", Decimal("0"))
        bearish = price < vwap and price < ema
        return RuleResult(
            rule=rule,
            passed=bearish,
            actual="bearish" if bearish else "neutral",
            required="bearish",
        )

    def _eval_volatility_above(self, rule: Rule, data: dict) -> RuleResult:
        bb_width_pct = data.get("bb_width_pct", 0)
        threshold = rule.threshold or 0.02
        passed = bb_width_pct >= threshold
        return RuleResult(
            rule=rule,
            passed=passed,
            actual=f"{bb_width_pct}%",
            required=f">= {threshold}%",
        )


def create_vwap_rsi_ema_ruleset() -> RuleSet:
    return RuleSet(
        name="VWAP + RSI + EMA Strategy",
        description="Three indicators: EMA for trend, VWAP for bias, RSI for timing",
        entry_rules=[
            Rule(name="Price above VWAP (bullish bias)", condition="vwap_above"),
            Rule(
                name="Price above EMA(8) (uptrend)", condition="ema_above", threshold=8
            ),
            Rule(
                name="RSI(3) below 30 (pullback)", condition="rsi_below", threshold=30
            ),
            Rule(
                name="Price within 1.5% of VWAP",
                condition="distance_within_pct",
                threshold=1.5,
            ),
        ],
        risk_rules=[
            Rule(
                name="Max position size", condition="distance_within_pct", threshold=5.0
            ),
        ],
    )
