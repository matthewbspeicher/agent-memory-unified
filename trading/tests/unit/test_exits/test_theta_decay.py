"""Tests for ThetaDecayExit rule."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from exits.rules import ThetaDecayExit


class TestThetaDecayExit:
    def test_exits_on_profit_target(self):
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,  # 50% profit
            stop_loss_pct=2.0,
            side="BUY",
        )
        # 50% profit: 0.50 -> 0.75
        assert rule.should_exit(Decimal("0.75")) is True

    def test_no_exit_below_profit_target(self):
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,
            side="BUY",
        )
        # 20% profit: 0.50 -> 0.60
        assert rule.should_exit(Decimal("0.60")) is False

    def test_exits_on_stop_loss(self):
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=0.2,  # 20% stop loss
            side="BUY",
        )
        # 40% loss: 0.50 -> 0.30
        assert rule.should_exit(Decimal("0.30")) is True

    def test_no_exit_above_stop_loss(self):
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=0.2,
            side="BUY",
        )
        # 10% loss: 0.50 -> 0.45
        assert rule.should_exit(Decimal("0.45")) is False

    def test_exits_on_dte_threshold(self):
        expires = datetime.now(timezone.utc) + timedelta(days=1)
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,
            min_dte=2,
            expires_at=expires,
            side="BUY",
        )
        # 1 day remaining, min_dte=2 -> should exit
        assert rule.should_exit(Decimal("0.52")) is True

    def test_no_exit_above_dte_threshold(self):
        expires = datetime.now(timezone.utc) + timedelta(days=5)
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,
            min_dte=2,
            expires_at=expires,
            side="BUY",
        )
        # 5 days remaining, min_dte=2 -> should not exit
        assert rule.should_exit(Decimal("0.52")) is False

    def test_sell_side_profit_calculation(self):
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,
            side="SELL",
        )
        # SELL at 0.50, price drops to 0.25 = 50% profit
        assert rule.should_exit(Decimal("0.25")) is True

    def test_sell_side_stop_loss_calculation(self):
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=0.2,
            side="SELL",
        )
        # SELL at 0.50, price rises to 0.60 = 20% loss
        assert rule.should_exit(Decimal("0.60")) is True

    def test_to_dict_serialization(self):
        expires = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=0.2,
            min_dte=2,
            expires_at=expires,
            side="BUY",
        )
        d = rule.to_dict()
        assert d["type"] == "theta_decay_exit"
        assert d["entry_price"] == "0.50"
        assert d["profit_target_pct"] == 0.5
        assert d["stop_loss_pct"] == 0.2
        assert d["min_dte"] == 2
        assert d["side"] == "BUY"

    def test_no_expires_at_skips_dte_check(self):
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,
            min_dte=2,
            expires_at=None,
            side="BUY",
        )
        # No expiry, so DTE check is skipped
        assert rule.should_exit(Decimal("0.52")) is False


class TestThetaDecayExitBoundaries:
    """Boundary tests that catch off-by-one regressions on thresholds."""

    def test_just_below_profit_target(self):
        """BUY: 49.98% profit must NOT exit at profit_target_pct=0.5."""
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,
            side="BUY",
        )
        # 0.7499 / 0.50 - 1 = 0.4998 profit
        assert rule.should_exit(Decimal("0.7499")) is False, (
            "49.98% profit tripped exit at target 50% — off-by-one regression"
        )

    def test_sell_just_above_profit_target(self):
        """SELL: price just above the exit point must NOT exit."""
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,
            side="SELL",
        )
        # 0.2501 -> (0.50-0.2501)/0.50 = 0.4998 profit
        assert rule.should_exit(Decimal("0.2501")) is False

    def test_sell_just_below_stop_loss(self):
        """SELL: loss just below stop_loss must NOT exit."""
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,
            side="SELL",
        )
        # 1.4999 -> (0.50-1.4999)/0.50 = -1.9998, not <= -2.0
        assert rule.should_exit(Decimal("1.4999")) is False

    def test_naive_expires_at_normalized_to_utc(self):
        """Naive datetime (no tzinfo) for expires_at must be normalized, not crash.

        Kalshi and similar APIs return naive datetimes. The rule must
        tolerate them and still correctly evaluate the DTE branch.
        """
        expires = (datetime.now(timezone.utc) + timedelta(days=5)).replace(tzinfo=None)
        rule = ThetaDecayExit(
            entry_price=Decimal("0.50"),
            profit_target_pct=0.5,
            stop_loss_pct=2.0,
            min_dte=2,
            expires_at=expires,
            side="BUY",
        )
        # 5 days out with min_dte=2 → DTE branch must not fire, and
        # profit is well below target, so the whole rule must return False.
        assert rule.should_exit(Decimal("0.51")) is False
