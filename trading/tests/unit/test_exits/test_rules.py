"""Tests for exit rules: StopLoss, TakeProfit, TrailingStop, TimeExit."""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from exits.rules import StopLoss, TakeProfit, TrailingStop, TimeExit


class TestStopLoss:
    def test_triggers_below_stop_price_for_buy(self):
        rule = StopLoss(stop_price=Decimal("95"), side="BUY")
        assert rule.should_exit(current_price=Decimal("94")) is True

    def test_no_trigger_above_stop_price_for_buy(self):
        rule = StopLoss(stop_price=Decimal("95"), side="BUY")
        assert rule.should_exit(current_price=Decimal("96")) is False

    def test_triggers_above_stop_price_for_sell(self):
        rule = StopLoss(stop_price=Decimal("105"), side="SELL")
        assert rule.should_exit(current_price=Decimal("106")) is True

    def test_no_trigger_below_stop_price_for_sell(self):
        rule = StopLoss(stop_price=Decimal("105"), side="SELL")
        assert rule.should_exit(current_price=Decimal("104")) is False

    def test_name_is_stop_loss(self):
        rule = StopLoss(stop_price=Decimal("95"))
        assert rule.name == "stop_loss"

    def test_to_dict(self):
        rule = StopLoss(stop_price=Decimal("90"), side="BUY")
        d = rule.to_dict()
        assert d["type"] == "stop_loss"
        assert d["stop_price"] == "90"


class TestTakeProfit:
    def test_triggers_above_target_for_buy(self):
        rule = TakeProfit(target_price=Decimal("120"), side="BUY")
        assert rule.should_exit(current_price=Decimal("121")) is True

    def test_no_trigger_below_target_for_buy(self):
        rule = TakeProfit(target_price=Decimal("120"), side="BUY")
        assert rule.should_exit(current_price=Decimal("119")) is False

    def test_triggers_below_target_for_sell(self):
        rule = TakeProfit(target_price=Decimal("80"), side="SELL")
        assert rule.should_exit(current_price=Decimal("79")) is True

    def test_no_trigger_above_target_for_sell(self):
        rule = TakeProfit(target_price=Decimal("80"), side="SELL")
        assert rule.should_exit(current_price=Decimal("81")) is False

    def test_name_is_take_profit(self):
        rule = TakeProfit(target_price=Decimal("120"))
        assert rule.name == "take_profit"

    def test_to_dict(self):
        rule = TakeProfit(target_price=Decimal("120"), side="BUY")
        d = rule.to_dict()
        assert d["type"] == "take_profit"
        assert d["target_price"] == "120"


class TestTrailingStop:
    def test_triggers_when_price_drops_by_trail_pct(self):
        rule = TrailingStop(trail_pct=Decimal("0.05"))
        rule.update(Decimal("110"))
        assert rule.should_exit(current_price=Decimal("104")) is True

    def test_no_trigger_within_trail(self):
        rule = TrailingStop(trail_pct=Decimal("0.05"))
        rule.update(Decimal("110"))
        assert rule.should_exit(current_price=Decimal("106")) is False

    def test_peak_updates_on_higher_price(self):
        rule = TrailingStop(trail_pct=Decimal("0.05"))
        rule.update(Decimal("100"))
        rule.update(Decimal("120"))
        # Peak is 120, 5% below = 114
        assert rule.should_exit(current_price=Decimal("113")) is True
        assert rule.should_exit(current_price=Decimal("115")) is False

    def test_name_is_trailing_stop(self):
        rule = TrailingStop(trail_pct=Decimal("0.05"))
        assert rule.name == "trailing_stop"

    def test_to_dict(self):
        rule = TrailingStop(trail_pct=Decimal("0.05"))
        d = rule.to_dict()
        assert d["type"] == "trailing_stop"
        assert d["trail_pct"] == "0.05"


class TestTimeExit:
    def test_triggers_after_expiry(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        rule = TimeExit(expires_at=past)
        assert rule.should_exit(current_price=Decimal("100"), current_time=datetime.now(timezone.utc)) is True

    def test_no_trigger_before_expiry(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        rule = TimeExit(expires_at=future)
        assert rule.should_exit(current_price=Decimal("100"), current_time=datetime.now(timezone.utc)) is False

    def test_name_is_time_exit(self):
        rule = TimeExit(expires_at=datetime.now(timezone.utc))
        assert rule.name == "time_exit"

    def test_to_dict(self):
        expires = datetime(2026, 12, 31, tzinfo=timezone.utc)
        rule = TimeExit(expires_at=expires)
        d = rule.to_dict()
        assert d["type"] == "time_exit"
        assert "expires_at" in d
