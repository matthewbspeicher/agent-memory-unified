"""Unit tests for PredictionTimeExit and ConvictionExitRule."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal


from exits.rules import ConvictionExitRule, PredictionTimeExit


# ---------------------------------------------------------------------------
# PredictionTimeExit
# ---------------------------------------------------------------------------


class TestPredictionTimeExit:
    """Tests for PredictionTimeExit rule."""

    def _future(self, days: float = 5.0) -> datetime:
        return datetime.now(timezone.utc) + timedelta(days=days)

    def _past(self, days: float = 1.0) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=days)

    def test_losing_buy_within_threshold_triggers(self):
        """BUY position that is losing and within max_days_to_expiry should trigger."""
        rule = PredictionTimeExit(expires_at=self._future(1.0), max_days_to_expiry=2)
        result = rule.should_exit(
            current_price=Decimal("0.40"),
            entry_price=Decimal("0.60"),
            side="BUY",
            current_time=datetime.now(timezone.utc),
        )
        assert result is True

    def test_winning_buy_within_threshold_no_trigger(self):
        """BUY position that is winning should NOT trigger even within threshold."""
        rule = PredictionTimeExit(expires_at=self._future(1.0), max_days_to_expiry=2)
        result = rule.should_exit(
            current_price=Decimal("0.80"),
            entry_price=Decimal("0.60"),
            side="BUY",
            current_time=datetime.now(timezone.utc),
        )
        assert result is False

    def test_losing_buy_outside_threshold_no_trigger(self):
        """Losing BUY position but more than max_days_to_expiry away should not trigger."""
        rule = PredictionTimeExit(expires_at=self._future(5.0), max_days_to_expiry=2)
        result = rule.should_exit(
            current_price=Decimal("0.30"),
            entry_price=Decimal("0.60"),
            side="BUY",
            current_time=datetime.now(timezone.utc),
        )
        assert result is False

    def test_losing_sell_within_threshold_triggers(self):
        """SELL position losing (current > entry) within threshold should trigger."""
        rule = PredictionTimeExit(expires_at=self._future(1.0), max_days_to_expiry=2)
        result = rule.should_exit(
            current_price=Decimal("0.80"),
            entry_price=Decimal("0.60"),
            side="SELL",
            current_time=datetime.now(timezone.utc),
        )
        assert result is True

    def test_winning_sell_within_threshold_no_trigger(self):
        """SELL position that is winning (current < entry) should NOT trigger."""
        rule = PredictionTimeExit(expires_at=self._future(1.0), max_days_to_expiry=2)
        result = rule.should_exit(
            current_price=Decimal("0.40"),
            entry_price=Decimal("0.60"),
            side="SELL",
            current_time=datetime.now(timezone.utc),
        )
        assert result is False

    def test_no_entry_price_returns_false(self):
        """When entry_price is not provided, should return False gracefully."""
        rule = PredictionTimeExit(expires_at=self._future(1.0), max_days_to_expiry=2)
        result = rule.should_exit(current_price=Decimal("0.30"))
        assert result is False

    def test_already_expired_and_losing_triggers(self):
        """Position that has already expired and is losing should trigger."""
        rule = PredictionTimeExit(expires_at=self._past(0.5), max_days_to_expiry=2)
        result = rule.should_exit(
            current_price=Decimal("0.20"),
            entry_price=Decimal("0.60"),
            side="BUY",
            current_time=datetime.now(timezone.utc),
        )
        assert result is True

    def test_name_is_prediction_time_exit(self):
        rule = PredictionTimeExit(expires_at=self._future(3.0))
        assert rule.name == "prediction_time_exit"

    def test_to_dict_round_trips(self):
        expires = datetime(2026, 6, 1, tzinfo=timezone.utc)
        rule = PredictionTimeExit(expires_at=expires, max_days_to_expiry=3)
        d = rule.to_dict()
        assert d["type"] == "prediction_time_exit"
        assert d["max_days_to_expiry"] == 3
        assert "expires_at" in d

    def test_exact_boundary_at_max_days_triggers(self):
        """At exactly max_days_to_expiry remaining (days_remaining == max_days_to_expiry), should trigger."""
        # days_remaining <= max_days_to_expiry → should trigger
        rule = PredictionTimeExit(expires_at=self._future(2.0), max_days_to_expiry=2)
        result = rule.should_exit(
            current_price=Decimal("0.30"),
            entry_price=Decimal("0.60"),
            side="BUY",
            current_time=datetime.now(timezone.utc),
        )
        assert result is True


# ---------------------------------------------------------------------------
# ConvictionExitRule
# ---------------------------------------------------------------------------


class TestConvictionExitRule:
    """Tests for ConvictionExitRule."""

    def test_buy_adverse_movement_beyond_threshold_triggers(self):
        """BUY: price moved down beyond threshold → triggers."""
        rule = ConvictionExitRule(
            original_confidence=0.80,
            entry_price=Decimal("0.70"),
            divergence_threshold=15.0,  # 15 cents
            agent_name="test_agent",
            side="BUY",
        )
        # Current price is 0.50: shift = (0.70 - 0.50) * 100 = 20 > 15 → trigger
        assert rule.should_exit(current_price=Decimal("0.50")) is True

    def test_buy_favorable_movement_no_trigger(self):
        """BUY: price moved UP (with thesis) → should NOT trigger."""
        rule = ConvictionExitRule(
            original_confidence=0.80,
            entry_price=Decimal("0.50"),
            divergence_threshold=15.0,
            agent_name="test_agent",
            side="BUY",
        )
        # Current price is 0.70: shift = (0.50 - 0.70) * 100 = -20 < 0 → no trigger
        assert rule.should_exit(current_price=Decimal("0.70")) is False

    def test_buy_adverse_movement_within_threshold_no_trigger(self):
        """BUY: price moved against thesis but within threshold → no trigger."""
        rule = ConvictionExitRule(
            original_confidence=0.75,
            entry_price=Decimal("0.60"),
            divergence_threshold=20.0,  # 20 cents
            agent_name="test_agent",
            side="BUY",
        )
        # Current price 0.50: shift = (0.60 - 0.50) * 100 = 10 < 20 → no trigger
        assert rule.should_exit(current_price=Decimal("0.50")) is False

    def test_sell_adverse_movement_beyond_threshold_triggers(self):
        """SELL: price moved UP against thesis beyond threshold → triggers."""
        rule = ConvictionExitRule(
            original_confidence=0.70,
            entry_price=Decimal("0.60"),
            divergence_threshold=10.0,  # 10 cents
            agent_name="test_agent",
            side="SELL",
        )
        # Current price 0.75: shift = (0.75 - 0.60) * 100 = 15 > 10 → trigger
        assert rule.should_exit(current_price=Decimal("0.75")) is True

    def test_sell_favorable_movement_no_trigger(self):
        """SELL: price moved DOWN (with thesis) → should NOT trigger."""
        rule = ConvictionExitRule(
            original_confidence=0.70,
            entry_price=Decimal("0.60"),
            divergence_threshold=10.0,
            agent_name="test_agent",
            side="SELL",
        )
        # Current price 0.40: shift = (0.40 - 0.60) * 100 = -20 < 0 → no trigger
        assert rule.should_exit(current_price=Decimal("0.40")) is False

    def test_sell_adverse_within_threshold_no_trigger(self):
        """SELL: price moved against thesis but within threshold → no trigger."""
        rule = ConvictionExitRule(
            original_confidence=0.70,
            entry_price=Decimal("0.60"),
            divergence_threshold=20.0,
            agent_name="test_agent",
            side="SELL",
        )
        # Current price 0.65: shift = (0.65 - 0.60) * 100 = 5 < 20 → no trigger
        assert rule.should_exit(current_price=Decimal("0.65")) is False

    def test_zero_movement_no_trigger(self):
        """No price movement → no trigger."""
        rule = ConvictionExitRule(
            original_confidence=0.80,
            entry_price=Decimal("0.50"),
            divergence_threshold=5.0,
            agent_name="test_agent",
            side="BUY",
        )
        assert rule.should_exit(current_price=Decimal("0.50")) is False

    def test_name_is_conviction_exit(self):
        rule = ConvictionExitRule(
            original_confidence=0.8,
            entry_price=Decimal("0.5"),
            divergence_threshold=10.0,
            agent_name="test",
        )
        assert rule.name == "conviction_exit"

    def test_to_dict_round_trips(self):
        rule = ConvictionExitRule(
            original_confidence=0.75,
            entry_price=Decimal("0.60"),
            divergence_threshold=15.0,
            agent_name="my_agent",
            side="BUY",
        )
        d = rule.to_dict()
        assert d["type"] == "conviction_exit"
        assert d["original_confidence"] == 0.75
        assert d["entry_price"] == "0.60"
        assert d["divergence_threshold"] == 15.0
        assert d["agent_name"] == "my_agent"
        assert d["side"] == "BUY"

    def test_directional_not_absolute_buy(self):
        """Directional check: favorable move should never trigger, even if large."""
        rule = ConvictionExitRule(
            original_confidence=0.80,
            entry_price=Decimal("0.50"),
            divergence_threshold=5.0,
            agent_name="test_agent",
            side="BUY",
        )
        # Price rose significantly (favorable for BUY) → shift is negative → no trigger
        assert rule.should_exit(current_price=Decimal("0.99")) is False

    def test_directional_not_absolute_sell(self):
        """Directional check: favorable SELL move (price down) should never trigger."""
        rule = ConvictionExitRule(
            original_confidence=0.80,
            entry_price=Decimal("0.70"),
            divergence_threshold=5.0,
            agent_name="test_agent",
            side="SELL",
        )
        # Price dropped significantly (favorable for SELL) → shift is negative → no trigger
        assert rule.should_exit(current_price=Decimal("0.01")) is False
