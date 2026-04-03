from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from learning.pnl import TradeTracker
from storage.performance import PerformanceSnapshot


@dataclass
class TriggerResult:
    trigger_name: str
    action: str
    metric: str
    value: float
    threshold: float


class TriggerEvaluator:
    def __init__(self, trigger_config: dict[str, Any]) -> None:
        self._config = trigger_config

    def evaluate(
        self,
        agent_name: str,
        snapshots: list[PerformanceSnapshot],
        closed_trades: list[dict],
        paper_stats: dict | None = None,
    ) -> list[TriggerResult]:
        results = []
        sorted_snapshots = sorted(snapshots, key=lambda s: s.timestamp, reverse=True)

        for trigger_name, rule in self._config.items():
            fired, metric, value, threshold = self._evaluate_rule(
                rule, sorted_snapshots, closed_trades, paper_stats
            )
            if fired:
                results.append(
                    TriggerResult(
                        trigger_name=trigger_name,
                        action=rule.get("action", "notify"),
                        metric=metric,
                        value=value,
                        threshold=threshold,
                    )
                )

        return results

    def _evaluate_rule(
        self,
        rule: dict,
        sorted_snapshots: list[PerformanceSnapshot],
        closed_trades: list[dict],
        paper_stats: dict | None,
    ) -> tuple[bool, str, float, float]:
        if "any_of" in rule:
            for condition in rule["any_of"]:
                fired, metric, value, threshold = self._evaluate_simple_condition(
                    condition, sorted_snapshots, closed_trades, paper_stats
                )
                if fired:
                    return True, metric, value, threshold
            return False, "", 0.0, 0.0

        if "all_of" in rule:
            last_metric, last_value, last_threshold = "", 0.0, 0.0
            for condition in rule["all_of"]:
                fired, metric, value, threshold = self._evaluate_simple_condition(
                    condition, sorted_snapshots, closed_trades, paper_stats
                )
                if not fired:
                    return False, "", 0.0, 0.0
                last_metric, last_value, last_threshold = metric, value, threshold
            return True, last_metric, last_value, last_threshold

        fired, metric, value, threshold = self._evaluate_simple_condition(
            rule, sorted_snapshots, closed_trades, paper_stats
        )
        return fired, metric, value, threshold

    def _evaluate_simple_condition(
        self,
        condition: dict,
        sorted_snapshots: list[PerformanceSnapshot],
        closed_trades: list[dict],
        paper_stats: dict | None,
    ) -> tuple[bool, str, float, float]:
        metric = condition.get("metric", "")
        threshold = float(condition.get("threshold", 0.0))
        comparison = condition.get("comparison", "below")
        consecutive_days = condition.get("consecutive_days")

        value = self._resolve_metric(metric, sorted_snapshots, closed_trades, paper_stats)

        if consecutive_days is not None:
            fired = self._check_consecutive_days(
                metric, threshold, consecutive_days, sorted_snapshots
            )
            return fired, metric, value, threshold

        if comparison == "below":
            fired = value < threshold
        elif comparison == "above":
            fired = value > threshold
        else:
            fired = value < threshold

        return fired, metric, value, threshold

    def _resolve_metric(
        self,
        metric: str,
        sorted_snapshots: list[PerformanceSnapshot],
        closed_trades: list[dict],
        paper_stats: dict | None,
    ) -> float:
        if metric.startswith("paper_") and paper_stats is not None:
            return float(paper_stats.get(metric[6:], 0.0))

        if metric == "consecutive_losses":
            return float(self._count_consecutive_losses(closed_trades))

        if metric == "sharpe_ratio_7d":
            return self._compute_sharpe_ratio_7d(sorted_snapshots)

        if sorted_snapshots:
            latest = sorted_snapshots[0]
            value = getattr(latest, metric, None)
            if value is not None:
                return float(value)

        return 0.0

    def _count_consecutive_losses(self, closed_trades: list[dict]) -> int:
        count = 0
        for trade in reversed(closed_trades):
            pnl = TradeTracker.compute_pnl(
                side=trade.get("side", "buy"),
                entry_price=Decimal(str(trade.get("entry_price", "0"))),
                exit_price=Decimal(str(trade.get("exit_price", "0"))),
                quantity=Decimal(str(trade.get("quantity", "0"))),
                entry_fees=Decimal(str(trade.get("entry_fees", "0"))),
                exit_fees=Decimal(str(trade.get("exit_fees", "0"))),
            )
            if pnl["net_pnl"] < 0:
                count += 1
            else:
                break
        return count

    def _compute_sharpe_ratio_7d(self, sorted_snapshots: list[PerformanceSnapshot]) -> float:
        last_7 = sorted_snapshots[:7]
        if len(last_7) < 5:
            return 0.0
        daily_pnls = [float(s.daily_pnl) for s in last_7]
        n = len(daily_pnls)
        mean = sum(daily_pnls) / n
        variance = sum((x - mean) ** 2 for x in daily_pnls) / n
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        return (mean / std) * math.sqrt(252)

    def _check_consecutive_days(
        self,
        metric: str,
        threshold: float,
        n: int,
        sorted_snapshots: list[PerformanceSnapshot],
    ) -> bool:
        if len(sorted_snapshots) < n:
            return False
        recent = sorted_snapshots[:n]
        return all(float(getattr(s, metric, 0.0)) < threshold for s in recent)
