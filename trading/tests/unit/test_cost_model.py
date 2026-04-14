"""Unit tests for CostModel."""

from decimal import Decimal

import pytest

from execution.cost_model import CostModel, ArbCostBreakdown, DEFAULT_SLIPPAGE_BPS


class TestCostModel:
    """Test CostModel calculations with default slippage applied."""

    @pytest.fixture
    def cost_model(self):
        return CostModel()

    def test_total_fee_rate(self, cost_model):
        """Combined fee rate should be 4% (2% Kalshi + 2% Polymarket)."""
        assert cost_model.total_fee_rate == Decimal("0.04")

    def test_total_fee_bps(self, cost_model):
        """Combined fee should be 400 bps."""
        assert cost_model.total_fee_bps == Decimal("400")

    def test_default_slippage_bps_constant(self):
        """Default slippage constant is the documented value."""
        assert DEFAULT_SLIPPAGE_BPS == Decimal("15")

    def test_min_gap_cents_with_default_slippage(self, cost_model):
        """Break-even with default slippage is (400 + 15) / 100 = 4.15 cents."""
        assert cost_model.min_gap_cents() == 4.15

    def test_min_gap_cents_with_explicit_zero_slippage(self, cost_model):
        """Break-even with zero slippage is 400/100 = 4 cents."""
        assert cost_model.min_gap_cents(slippage_bps=Decimal("0")) == 4.0

    def test_expected_profit_bps_at_old_break_even_now_negative(self, cost_model):
        """At 4c gap, default slippage makes it unprofitable (-15 bps)."""
        result = cost_model.expected_profit_bps(4.0)
        assert result == Decimal("-15")

    def test_expected_profit_bps_profitable_with_default_slippage(self, cost_model):
        """At 5c gap: 500 gross - 400 fees - 15 slip = 85 bps."""
        result = cost_model.expected_profit_bps(5.0)
        assert result == Decimal("85")

    def test_expected_profit_bps_unprofitable(self, cost_model):
        """At 3c gap: 300 gross - 400 fees - 15 slip = -115 bps."""
        result = cost_model.expected_profit_bps(3.0)
        assert result == Decimal("-115")

    def test_expected_profit_bps_with_explicit_slippage(self, cost_model):
        """Caller can override slippage to suppress the default."""
        result = cost_model.expected_profit_bps(5.0, slippage_bps=Decimal("0"))
        assert result == Decimal("100")

    def test_expected_profit_bps_with_decimal_input(self, cost_model):
        """Should accept Decimal input."""
        result = cost_model.expected_profit_bps(Decimal("5.5"))
        assert result == Decimal("135")  # 550 - 400 - 15

    def test_calculate_breakdown_profitable(self, cost_model):
        """Breakdown for a profitable trade (5c gap, default slippage)."""
        breakdown = cost_model.calculate_breakdown(5.0, quantity=10)

        assert breakdown.gross_gap_bps == Decimal("500")
        assert breakdown.kalshi_fee_bps == Decimal("200")
        assert breakdown.polymarket_fee_bps == Decimal("200")
        assert breakdown.total_fee_bps == Decimal("400")
        assert breakdown.slippage_bps == Decimal("15")
        assert breakdown.slippage_is_estimated is True
        assert breakdown.net_profit_bps == Decimal("85")
        assert breakdown.is_profitable is True

    def test_calculate_breakdown_with_supplied_slippage_not_estimated(self, cost_model):
        """Caller-supplied slippage clears the estimated flag."""
        breakdown = cost_model.calculate_breakdown(5.0, slippage_bps=Decimal("10"))
        assert breakdown.slippage_is_estimated is False
        assert breakdown.slippage_bps == Decimal("10")
        assert breakdown.net_profit_bps == Decimal("90")

    def test_calculate_breakdown_unprofitable(self, cost_model):
        """Breakdown for an unprofitable trade (3c gap)."""
        breakdown = cost_model.calculate_breakdown(3.0)
        assert breakdown.gross_gap_bps == Decimal("300")
        assert breakdown.net_profit_bps == Decimal("-115")
        assert breakdown.is_profitable is False

    def test_should_execute_requires_positive_profit(self, cost_model):
        """Should not execute at old break-even (now negative with slippage)."""
        assert cost_model.should_execute(4.0) is False

    def test_should_execute_with_positive_threshold(self, cost_model):
        """5c gap = 85 bps net; 50 bps threshold passes."""
        assert cost_model.should_execute(5.0, min_profit_bps=50.0) is True

    def test_should_execute_below_threshold(self, cost_model):
        """5c gap = 85 bps net; 100 bps threshold fails."""
        assert cost_model.should_execute(5.0, min_profit_bps=100.0) is False

    def test_should_execute_with_zero_threshold_needs_positive_net(self, cost_model):
        """Zero threshold: still needs strictly positive net profit."""
        assert cost_model.should_execute(5.0, min_profit_bps=0.0) is True

    def test_custom_default_slippage_in_constructor(self):
        """Constructor override changes the default slippage applied."""
        model = CostModel(default_slippage_bps=Decimal("50"))
        # 5c gap = 500 - 400 - 50 = 50 bps
        assert model.expected_profit_bps(5.0) == Decimal("50")
        assert model.min_gap_cents() == 4.5


class TestArbCostBreakdown:
    """Test ArbCostBreakdown dataclass."""

    def test_is_frozen(self):
        """Breakdown should be immutable."""
        breakdown = ArbCostBreakdown(
            gross_gap_bps=Decimal("500"),
            kalshi_fee_bps=Decimal("200"),
            polymarket_fee_bps=Decimal("200"),
            total_fee_bps=Decimal("400"),
            slippage_bps=Decimal("15"),
            net_profit_bps=Decimal("85"),
            is_profitable=True,
            slippage_is_estimated=True,
        )
        with pytest.raises(AttributeError):
            breakdown.net_profit_bps = Decimal("999")
