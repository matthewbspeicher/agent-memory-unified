"""Unit tests for PreExpiryExit, ProbabilityTrailingStop, and PartialExitRule."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from exits.rules import (
    PreExpiryExit,
    ProbabilityTrailingStop,
    PartialExitRule,
    parse_rule,
)


def _future(hours: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _past(hours: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


# ---------------------------------------------------------------------------
# PreExpiryExit
# ---------------------------------------------------------------------------

class TestPreExpiryExit:
    def test_well_before_window_no_trigger(self):
        """5 hours remaining, 4-hour window → should NOT trigger."""
        rule = PreExpiryExit(expires_at=_future(5.0), hours_before_expiry=4.0)
        assert rule.should_exit(Decimal("0.60")) is False

    def test_at_window_boundary_triggers(self):
        """Exactly 4 hours remaining, 4-hour window → should trigger."""
        rule = PreExpiryExit(expires_at=_future(4.0), hours_before_expiry=4.0)
        assert rule.should_exit(Decimal("0.60")) is True

    def test_inside_window_triggers(self):
        """3 hours remaining, 4-hour window → should trigger."""
        rule = PreExpiryExit(expires_at=_future(3.0), hours_before_expiry=4.0)
        assert rule.should_exit(Decimal("0.60")) is True

    def test_at_zero_remaining_triggers(self):
        """0 hours remaining (contract expiring now) → should trigger."""
        rule = PreExpiryExit(expires_at=_future(0.0), hours_before_expiry=4.0)
        assert rule.should_exit(Decimal("0.60")) is True

    def test_past_expiry_no_trigger(self):
        """Contract already expired (negative remaining) → should NOT trigger (avoid double-exit)."""
        rule = PreExpiryExit(expires_at=_past(1.0), hours_before_expiry=4.0)
        assert rule.should_exit(Decimal("0.60")) is False

    def test_triggers_regardless_of_pnl(self):
        """Triggers whether position is winning or losing."""
        rule = PreExpiryExit(expires_at=_future(2.0), hours_before_expiry=4.0)
        assert rule.should_exit(Decimal("0.95")) is True  # winning
        assert rule.should_exit(Decimal("0.05")) is True  # losing

    def test_current_time_kwarg_respected(self):
        """Explicit current_time overrides wall clock."""
        expires = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        rule = PreExpiryExit(expires_at=expires, hours_before_expiry=4.0)
        # 2 hours before expiry → inside window → trigger
        t_inside = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
        assert rule.should_exit(Decimal("0.50"), current_time=t_inside) is True
        # 6 hours before expiry → outside window → no trigger
        t_outside = datetime(2026, 6, 1, 6, 0, tzinfo=timezone.utc)
        assert rule.should_exit(Decimal("0.50"), current_time=t_outside) is False

    def test_name(self):
        rule = PreExpiryExit(expires_at=_future(10.0))
        assert rule.name == "pre_expiry_exit"

    def test_to_dict(self):
        expires = datetime(2026, 6, 1, tzinfo=timezone.utc)
        rule = PreExpiryExit(expires_at=expires, hours_before_expiry=2.0)
        d = rule.to_dict()
        assert d["type"] == "pre_expiry_exit"
        assert d["hours_before_expiry"] == 2.0
        assert "expires_at" in d

    def test_parse_rule_round_trip(self):
        expires = datetime(2026, 6, 1, tzinfo=timezone.utc)
        rule = PreExpiryExit(expires_at=expires, hours_before_expiry=3.5)
        parsed = parse_rule(rule.to_dict())
        assert isinstance(parsed, PreExpiryExit)
        assert parsed.hours_before_expiry == 3.5

    def test_exit_fraction_is_full(self):
        rule = PreExpiryExit(expires_at=_future(1.0))
        assert rule.exit_fraction == 1.0

    def test_naive_expires_at_treated_as_utc(self):
        """Naive datetime in expires_at should be treated as UTC, not raise."""
        expires_naive = datetime(2026, 6, 1, 10, 0)  # no tzinfo
        rule = PreExpiryExit(expires_at=expires_naive, hours_before_expiry=4.0)
        # Should not raise; result is not tested for exact value
        result = rule.should_exit(Decimal("0.50"))
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# ProbabilityTrailingStop
# ---------------------------------------------------------------------------

class TestProbabilityTrailingStop:
    def test_no_peak_no_trigger(self):
        """Before any update(), peak is 0 → should never trigger."""
        rule = ProbabilityTrailingStop(trail_pp=15.0)
        assert rule.should_exit(Decimal("0.10")) is False

    def test_peak_updates_on_higher_price(self):
        """update() should advance the peak when price exceeds previous peak."""
        rule = ProbabilityTrailingStop(trail_pp=15.0)
        rule.update(Decimal("0.60"))
        rule.update(Decimal("0.75"))
        rule.update(Decimal("0.70"))  # lower than peak — should not update
        # peak should be 0.75; stop = 0.75 - 0.15 = 0.60
        assert rule.should_exit(Decimal("0.59")) is True
        assert rule.should_exit(Decimal("0.61")) is False

    def test_trail_pp_applied_correctly(self):
        """trail_pp=20 → stop is peak - 0.20."""
        rule = ProbabilityTrailingStop(trail_pp=20.0)
        rule.update(Decimal("0.80"))
        # stop = 0.80 - 0.20 = 0.60
        assert rule.should_exit(Decimal("0.59")) is True
        assert rule.should_exit(Decimal("0.61")) is False

    def test_quiet_zone_suppresses_near_zero(self):
        """Price in quiet zone near 0 → should NOT trigger even if below stop."""
        rule = ProbabilityTrailingStop(trail_pp=15.0, quiet_zone=0.05)
        rule.update(Decimal("0.50"))
        # stop = 0.50 - 0.15 = 0.35; current = 0.03 is below stop but in quiet zone
        assert rule.should_exit(Decimal("0.03")) is False

    def test_quiet_zone_suppresses_near_one(self):
        """Price in quiet zone near 1 → should NOT trigger."""
        rule = ProbabilityTrailingStop(trail_pp=15.0, quiet_zone=0.05)
        rule.update(Decimal("0.96"))
        # price is 0.97: > 1 - 0.05 = 0.95 → in quiet zone → no trigger
        assert rule.should_exit(Decimal("0.97")) is False

    def test_mid_range_triggers_normally(self):
        """Price at 0.50 is outside quiet zone — should trigger normally."""
        rule = ProbabilityTrailingStop(trail_pp=10.0, quiet_zone=0.05)
        rule.update(Decimal("0.70"))
        # stop = 0.70 - 0.10 = 0.60; current = 0.55 → trigger
        assert rule.should_exit(Decimal("0.55")) is True

    def test_name(self):
        rule = ProbabilityTrailingStop(trail_pp=15.0)
        assert rule.name == "probability_trailing_stop"

    def test_to_dict_includes_peak(self):
        rule = ProbabilityTrailingStop(trail_pp=15.0, side="BUY", quiet_zone=0.05)
        rule.update(Decimal("0.65"))
        d = rule.to_dict()
        assert d["type"] == "probability_trailing_stop"
        assert d["trail_pp"] == 15.0
        assert d["quiet_zone"] == 0.05
        assert d["peak"] == 0.65

    def test_parse_rule_round_trip(self):
        rule = ProbabilityTrailingStop(trail_pp=20.0, quiet_zone=0.08)
        rule.update(Decimal("0.75"))
        parsed = parse_rule(rule.to_dict())
        assert isinstance(parsed, ProbabilityTrailingStop)
        assert parsed.trail_pp == 20.0
        assert parsed.quiet_zone == 0.08
        assert parsed._peak == 0.75

    def test_exit_fraction_is_full(self):
        rule = ProbabilityTrailingStop(trail_pp=10.0)
        assert rule.exit_fraction == 1.0


# ---------------------------------------------------------------------------
# PartialExitRule
# ---------------------------------------------------------------------------

class TestPartialExitRule:
    def test_buy_triggers_at_target(self):
        """BUY partial exit triggers when current_price >= target_price."""
        rule = PartialExitRule(target_price=Decimal("0.80"), fraction=0.5)
        assert rule.should_exit(Decimal("0.80")) is True
        assert rule.should_exit(Decimal("0.85")) is True

    def test_buy_no_trigger_below_target(self):
        """BUY partial exit does NOT trigger below target."""
        rule = PartialExitRule(target_price=Decimal("0.80"), fraction=0.5)
        assert rule.should_exit(Decimal("0.79")) is False

    def test_sell_triggers_at_or_below_target(self):
        """SELL partial exit triggers when current_price <= target_price."""
        rule = PartialExitRule(target_price=Decimal("0.40"), fraction=0.5, side="SELL")
        assert rule.should_exit(Decimal("0.40")) is True
        assert rule.should_exit(Decimal("0.35")) is True

    def test_sell_no_trigger_above_target(self):
        """SELL partial exit does NOT trigger above target."""
        rule = PartialExitRule(target_price=Decimal("0.40"), fraction=0.5, side="SELL")
        assert rule.should_exit(Decimal("0.41")) is False

    def test_fires_only_once(self):
        """After mark_triggered(), should_exit() always returns False."""
        rule = PartialExitRule(target_price=Decimal("0.80"), fraction=0.5)
        assert rule.should_exit(Decimal("0.85")) is True
        rule.mark_triggered()
        assert rule.should_exit(Decimal("0.90")) is False
        assert rule.should_exit(Decimal("0.85")) is False

    def test_mark_triggered_is_idempotent(self):
        """Calling mark_triggered() twice is safe."""
        rule = PartialExitRule(target_price=Decimal("0.80"), fraction=0.5)
        rule.mark_triggered()
        rule.mark_triggered()
        assert rule.should_exit(Decimal("0.90")) is False

    def test_exit_fraction_returns_configured_value(self):
        """exit_fraction should return the configured fraction, not 1.0."""
        rule = PartialExitRule(target_price=Decimal("0.80"), fraction=0.33)
        assert rule.exit_fraction == 0.33

    def test_name(self):
        rule = PartialExitRule(target_price=Decimal("0.70"), fraction=0.5)
        assert rule.name == "partial_exit"

    def test_to_dict(self):
        rule = PartialExitRule(target_price=Decimal("0.80"), fraction=0.5, side="BUY")
        rule.mark_triggered()
        d = rule.to_dict()
        assert d["type"] == "partial_exit"
        assert d["target_price"] == "0.80"
        assert d["fraction"] == 0.5
        assert d["triggered"] is True

    def test_parse_rule_round_trip_not_triggered(self):
        rule = PartialExitRule(target_price=Decimal("0.75"), fraction=0.33, side="BUY")
        parsed = parse_rule(rule.to_dict())
        assert isinstance(parsed, PartialExitRule)
        assert parsed.fraction == 0.33
        assert parsed._triggered is False

    def test_parse_rule_round_trip_triggered(self):
        rule = PartialExitRule(target_price=Decimal("0.75"), fraction=0.33)
        rule.mark_triggered()
        parsed = parse_rule(rule.to_dict())
        assert isinstance(parsed, PartialExitRule)
        assert parsed._triggered is True
        assert parsed.should_exit(Decimal("0.90")) is False
