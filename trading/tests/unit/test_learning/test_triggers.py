from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from learning.triggers import TriggerEvaluator
from storage.performance import PerformanceSnapshot


def _make_snapshot(
    daily_pnl_pct: float,
    max_drawdown: float = 0.0,
    daily_pnl: float = 0.0,
    offset_days: int = 0,
) -> PerformanceSnapshot:
    ts = datetime(2026, 3, 25, tzinfo=timezone.utc) - timedelta(days=offset_days)
    return PerformanceSnapshot(
        agent_name="test-agent",
        timestamp=ts,
        opportunities_generated=10,
        opportunities_executed=5,
        win_rate=0.5,
        daily_pnl_pct=daily_pnl_pct,
        max_drawdown=max_drawdown,
        daily_pnl=Decimal(str(daily_pnl)),
    )


def _make_trade(
    entry: float, exit_: float, side: str = "buy", qty: float = 1.0
) -> dict:
    return {
        "side": side,
        "entry_price": str(entry),
        "exit_price": str(exit_),
        "quantity": str(qty),
        "entry_fees": "0",
        "exit_fees": "0",
    }


class TestTriggerEvaluator:
    def test_underperformance_alert_triggers_after_consecutive_days(self):
        config = {
            "underperformance_alert": {
                "metric": "daily_pnl_pct",
                "threshold": -0.02,
                "consecutive_days": 3,
                "action": "notify",
            }
        }
        snapshots = [
            _make_snapshot(daily_pnl_pct=-0.03, offset_days=0),
            _make_snapshot(daily_pnl_pct=-0.03, offset_days=1),
            _make_snapshot(daily_pnl_pct=-0.03, offset_days=2),
        ]
        evaluator = TriggerEvaluator(config)
        results = evaluator.evaluate("test-agent", snapshots, [])
        assert len(results) == 1
        assert results[0].trigger_name == "underperformance_alert"
        assert results[0].action == "notify"
        assert results[0].metric == "daily_pnl_pct"

    def test_no_trigger_when_not_enough_consecutive_days(self):
        config = {
            "underperformance_alert": {
                "metric": "daily_pnl_pct",
                "threshold": -0.02,
                "consecutive_days": 3,
                "action": "notify",
            }
        }
        snapshots = [
            _make_snapshot(daily_pnl_pct=-0.03, offset_days=0),
            _make_snapshot(
                daily_pnl_pct=0.01, offset_days=1
            ),  # positive — breaks streak
            _make_snapshot(daily_pnl_pct=-0.03, offset_days=2),
        ]
        evaluator = TriggerEvaluator(config)
        results = evaluator.evaluate("test-agent", snapshots, [])
        assert results == []

    def test_max_drawdown_trigger(self):
        config = {
            "high_drawdown": {
                "any_of": [
                    {
                        "metric": "max_drawdown",
                        "threshold": 0.15,
                        "comparison": "above",
                    },
                ],
                "action": "disable",
            }
        }
        snapshots = [_make_snapshot(daily_pnl_pct=0.0, max_drawdown=0.20)]
        evaluator = TriggerEvaluator(config)
        results = evaluator.evaluate("test-agent", snapshots, [])
        assert len(results) == 1
        assert results[0].trigger_name == "high_drawdown"
        assert results[0].action == "disable"
        assert results[0].metric == "max_drawdown"
        assert results[0].value == pytest.approx(0.20)
        assert results[0].threshold == pytest.approx(0.15)

    def test_consecutive_losses_trigger(self):
        config = {
            "loss_streak": {
                "any_of": [
                    {
                        "metric": "consecutive_losses",
                        "threshold": 2,
                        "comparison": "above",
                    },
                ],
                "action": "adjust",
            }
        }
        trades = [
            _make_trade(entry=100.0, exit_=90.0),  # loss
            _make_trade(entry=100.0, exit_=90.0),  # loss
            _make_trade(entry=100.0, exit_=90.0),  # loss
        ]
        evaluator = TriggerEvaluator(config)
        results = evaluator.evaluate("test-agent", [], trades)
        assert len(results) == 1
        assert results[0].trigger_name == "loss_streak"
        assert results[0].metric == "consecutive_losses"
        assert results[0].value == pytest.approx(3.0)
