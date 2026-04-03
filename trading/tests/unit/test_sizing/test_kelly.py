"""Tests for Kelly criterion position sizing math."""
import pytest
from decimal import Decimal
from sizing.kelly import kelly_fraction, compute_position_size


class TestKellyFraction:
    def test_coin_flip_with_edge(self):
        # 60% win, 1:1 payoff → Kelly = 0.20
        f = kelly_fraction(win_rate=0.6, avg_win=Decimal("100"), avg_loss=Decimal("100"))
        assert abs(f - 0.20) < 0.01

    def test_high_win_rate(self):
        # 70% win, 2:1 payoff → Kelly = 0.55
        f = kelly_fraction(win_rate=0.7, avg_win=Decimal("200"), avg_loss=Decimal("100"))
        assert abs(f - 0.55) < 0.01

    def test_no_edge_returns_zero(self):
        f = kelly_fraction(win_rate=0.5, avg_win=Decimal("100"), avg_loss=Decimal("100"))
        assert f == 0.0

    def test_negative_edge_clamped(self):
        f = kelly_fraction(win_rate=0.4, avg_win=Decimal("100"), avg_loss=Decimal("100"))
        assert f == 0.0

    def test_zero_losses(self):
        f = kelly_fraction(win_rate=1.0, avg_win=Decimal("100"), avg_loss=Decimal("0"))
        assert f == 1.0


class TestComputePositionSize:
    def test_basic_sizing(self):
        qty = compute_position_size(
            win_rate=0.6, avg_win=Decimal("100"), avg_loss=Decimal("100"),
            bankroll=Decimal("10000"), price=Decimal("100"),
            kelly_multiplier=Decimal("0.5"),
        )
        # Kelly=0.20, half=0.10, 10% of 10000 / 100 = 10
        assert qty == Decimal("10")

    def test_caps_at_max_pct(self):
        qty = compute_position_size(
            win_rate=0.9, avg_win=Decimal("1000"), avg_loss=Decimal("10"),
            bankroll=Decimal("10000"), price=Decimal("100"),
            kelly_multiplier=Decimal("0.5"), max_pct=Decimal("0.05"),
        )
        assert qty <= Decimal("5")

    def test_no_edge_returns_zero(self):
        qty = compute_position_size(
            win_rate=0.5, avg_win=Decimal("100"), avg_loss=Decimal("100"),
            bankroll=Decimal("10000"), price=Decimal("100"),
        )
        assert qty == Decimal("0")
