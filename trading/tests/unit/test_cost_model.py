"""Unit tests for CostModel."""

from decimal import Decimal

import pytest

from execution.cost_model import CostModel, ArbCostBreakdown


class TestCostModel:
    """Test CostModel calculations."""

    @pytest.fixture
    def cost_model(self):
        return CostModel()

    def test_total_fee_rate(self, cost_model):
        """Combined fee rate should be 4% (2% Kalshi + 2% Polymarket)."""
        assert cost_model.total_fee_rate == Decimal("0.04")

    def test_total_fee_bps(self, cost_model):
        """Combined fee should be 400 bps."""
        assert cost_model.total_fee_bps == Decimal("400")

    def test_min_gap_cents(self, cost_model):
        """Minimum gap to break even is 4 cents."""
        assert cost_model.min_gap_cents() == 4.0

    def test_expected_profit_bps_at_break_even(self, cost_model):
        """At 4 cent gap, profit should be 0 (break-even)."""
        result = cost_model.expected_profit_bps(4.0)
        assert result == Decimal("0")

    def test_expected_profit_bps_profitable(self, cost_model):
        """At 5 cent gap, profit should be 100 bps."""
        result = cost_model.expected_profit_bps(5.0)
        assert result == Decimal("100")

    def test_expected_profit_bps_unprofitable(self, cost_model):
        """At 3 cent gap, profit should be -100 bps (loss)."""
        result = cost_model.expected_profit_bps(3.0)
        assert result == Decimal("-100")

    def test_expected_profit_bps_with_decimal_input(self, cost_model):
        """Should accept Decimal input."""
        result = cost_model.expected_profit_bps(Decimal("5.5"))
        assert result == Decimal("150")

    def test_calculate_breakdown_profitable(self, cost_model):
        """Breakdown for a profitable trade (5 cent gap)."""
        breakdown = cost_model.calculate_breakdown(5.0, quantity=10)

        assert breakdown.gross_gap_bps == Decimal("500")
        assert breakdown.kalshi_fee_bps == Decimal("200")
        assert breakdown.polymarket_fee_bps == Decimal("200")
        assert breakdown.total_fee_bps == Decimal("400")
        assert breakdown.net_profit_bps == Decimal("100")
        assert breakdown.is_profitable is True

    def test_calculate_breakdown_unprofitable(self, cost_model):
        """Breakdown for an unprofitable trade (3 cent gap)."""
        breakdown = cost_model.calculate_breakdown(3.0)

        assert breakdown.gross_gap_bps == Decimal("300")
        assert breakdown.net_profit_bps == Decimal("-100")
        assert breakdown.is_profitable is False

    def test_calculate_breakdown_break_even(self, cost_model):
        """Breakdown at break-even (4 cent gap)."""
        breakdown = cost_model.calculate_breakdown(4.0)

        assert breakdown.net_profit_bps == Decimal("0")
        assert breakdown.is_profitable is False

    def test_should_execute_at_break_even(self, cost_model):
        """Should not execute at break-even with default threshold."""
        assert cost_model.should_execute(4.0) is False

    def test_should_execute_with_positive_threshold(self, cost_model):
        """Should execute when profit exceeds threshold."""
        # 5 cent gap = 100 bps profit, threshold 50 bps
        assert cost_model.should_execute(5.0, min_profit_bps=50.0) is True

    def test_should_execute_below_threshold(self, cost_model):
        """Should not execute when profit below threshold."""
        # 5 cent gap = 100 bps profit, threshold 150 bps
        assert cost_model.should_execute(5.0, min_profit_bps=150.0) is False

    def test_should_execute_with_zero_threshold(self, cost_model):
        """With zero threshold, should execute any profitable trade."""
        assert cost_model.should_execute(5.0, min_profit_bps=0.0) is True


class TestArbCostBreakdown:
    """Test ArbCostBreakdown dataclass."""

    def test_is_frozen(self):
        """Breakdown should be immutable."""
        breakdown = ArbCostBreakdown(
            gross_gap_bps=Decimal("500"),
            kalshi_fee_bps=Decimal("200"),
            polymarket_fee_bps=Decimal("200"),
            total_fee_bps=Decimal("400"),
            net_profit_bps=Decimal("100"),
            is_profitable=True,
        )
        with pytest.raises(AttributeError):
            breakdown.net_profit_bps = Decimal("999")
