"""Unit tests for RiskAnalytics module."""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from trading.risk.analytics import (
    RiskAnalytics,
    RiskLimit,
    RiskViolation,
    PortfolioRisk,
    PositionRisk,
    RiskMetric,
)


class TestRiskAnalyticsVaR:
    """Tests for VaR calculation."""

    def test_var_95_basic(self):
        """Test 95% VaR calculation with basic returns."""
        analytics = RiskAnalytics()
        returns = [-0.05, -0.02, 0.01, -0.01, 0.02, -0.03, 0.01, -0.04, 0.01, 0.01]

        var = analytics.calculate_var(returns, 0.95)

        assert var > 0
        assert var <= 0.05  # Should be at most the worst return

    def test_var_99_stricter(self):
        """Test that 99% VaR is higher than 95% VaR."""
        analytics = RiskAnalytics()
        returns = [-0.05, -0.02, 0.01, -0.01, 0.02, -0.03, 0.01, -0.04, 0.01, 0.01]

        var_95 = analytics.calculate_var(returns, 0.95)
        var_99 = analytics.calculate_var(returns, 0.99)

        assert var_99 >= var_95

    def test_var_insufficient_data(self):
        """Test VaR with insufficient data returns 0."""
        analytics = RiskAnalytics()

        assert analytics.calculate_var([], 0.95) == 0.0
        assert analytics.calculate_var([0.01, 0.02], 0.95) == 0.0  # Less than 10

    def test_cvar_calculation(self):
        """Test Conditional VaR (Expected Shortfall)."""
        analytics = RiskAnalytics()
        returns = [-0.05, -0.02, 0.01, -0.01, 0.02, -0.03, 0.01, -0.04, 0.01, 0.01]

        cvar = analytics.calculate_cvar(returns, 0.95)

        # CVaR should be >= VaR (average of tail losses)
        var = analytics.calculate_var(returns, 0.95)
        assert cvar >= var


class TestRiskAnalyticsDrawdown:
    """Tests for drawdown tracking."""

    def test_drawdown_basic(self):
        """Test basic drawdown calculation."""
        analytics = RiskAnalytics()

        # Simulate equity going up then down
        analytics.update_equity(Decimal("10000"))
        analytics.update_equity(Decimal("10500"))
        analytics.update_equity(Decimal("11000"))
        analytics.update_equity(Decimal("10000"))  # Drawdown from peak
        analytics.update_equity(Decimal("9500"))

        current_dd, max_dd = analytics.calculate_drawdown()

        assert current_dd > 0  # Current equity below peak
        assert max_dd > 0  # Max should be > 0
        assert current_dd <= max_dd

    def test_no_drawdown_while_going_up(self):
        """Test drawdown when equity keeps rising."""
        analytics = RiskAnalytics()

        analytics.update_equity(Decimal("10000"))
        analytics.update_equity(Decimal("10500"))
        analytics.update_equity(Decimal("11000"))

        current_dd, max_dd = analytics.calculate_drawdown()

        assert current_dd == 0.0  # No drawdown while above peak
        assert max_dd == 0.0  # No max drawdown either

    def test_peak_tracking(self):
        """Test peak equity is correctly tracked."""
        analytics = RiskAnalytics()

        analytics.update_equity(Decimal("10000"))
        analytics.update_equity(Decimal("9000"))  # Below initial
        analytics.update_equity(Decimal("12000"))  # New peak
        analytics.update_equity(Decimal("11000"))  # Below peak

        # Peak should be 12000
        _, max_dd = analytics.calculate_drawdown()

        # Drawdown from 12000 to 11000 = ~8.3%
        assert max_dd > 0


class TestRiskAnalyticsPortfolio:
    """Tests for portfolio risk calculations."""

    def test_portfolio_risk_empty(self):
        """Test portfolio risk with no positions."""
        analytics = RiskAnalytics()

        risk = analytics.calculate_portfolio_risk([], {})

        assert risk.total_positions == 0
        assert risk.total_long_notional == 0
        assert risk.total_short_notional == 0

    def test_portfolio_risk_single_long(self):
        """Test portfolio risk with single long position."""
        analytics = RiskAnalytics()
        analytics.update_equity(Decimal("10000"))  # Set starting equity

        positions = [{"symbol": "AAPL", "quantity": 100, "avg_price": 150.0}]
        prices = {"AAPL": Decimal("160.0")}

        risk = analytics.calculate_portfolio_risk(positions, prices)

        assert risk.total_positions == 1
        assert risk.long_positions == 1
        assert risk.short_positions == 0
        assert risk.total_long_notional == Decimal("16000")
        assert risk.gross_notional == Decimal("16000")

    def test_portfolio_risk_single_short(self):
        """Test portfolio risk with single short position."""
        analytics = RiskAnalytics()
        analytics.update_equity(Decimal("10000"))

        positions = [{"symbol": "AAPL", "quantity": -100, "avg_price": 160.0}]
        prices = {"AAPL": Decimal("150.0")}

        risk = analytics.calculate_portfolio_risk(positions, prices)

        assert risk.total_positions == 1
        assert risk.long_positions == 0
        assert risk.short_positions == 1
        assert risk.total_short_notional == Decimal("15000")

    def test_portfolio_risk_long_short_balanced(self):
        """Test portfolio with balanced long/short."""
        analytics = RiskAnalytics()
        analytics.update_equity(Decimal("20000"))

        positions = [
            {"symbol": "AAPL", "quantity": 100, "avg_price": 150.0},
            {"symbol": "GOOG", "quantity": -50, "avg_price": 200.0},
        ]
        prices = {
            "AAPL": Decimal("160.0"),
            "GOOG": Decimal("190.0"),
        }

        risk = analytics.calculate_portfolio_risk(positions, prices)

        assert risk.total_positions == 2
        # AAPL: long 16000, GOOG: short 9500
        assert risk.total_long_notional == Decimal("16000")
        assert risk.total_short_notional == Decimal("9500")
        # Net = 16000 - 9500 = 6500
        assert risk.net_notional == Decimal("6500")
        # Gross = 16000 + 9500 = 25500
        assert risk.gross_notional == Decimal("25500")

    def test_position_risk_details(self):
        """Test that position-level risk is captured."""
        analytics = RiskAnalytics()
        analytics.update_equity(Decimal("10000"))

        positions = [{"symbol": "AAPL", "quantity": 100, "avg_price": 150.0}]
        prices = {"AAPL": Decimal("160.0")}

        risk = analytics.calculate_portfolio_risk(positions, prices)

        assert len(risk.position_risks) == 1
        pos = risk.position_risks[0]

        assert pos.symbol == "AAPL"
        assert pos.quantity == Decimal("100")
        assert pos.avg_price == Decimal("150")
        assert pos.current_price == Decimal("160")
        assert pos.market_value == Decimal("16000")
        assert pos.unrealized_pnl == Decimal("1000")  # (160-150) * 100

    def test_leverage_calculation(self):
        """Test leverage is calculated correctly."""
        analytics = RiskAnalytics()
        analytics.update_equity(Decimal("10000"))

        positions = [
            {"symbol": "AAPL", "quantity": 50, "avg_price": 150.0},
            {"symbol": "GOOG", "quantity": 50, "avg_price": 200.0},
        ]
        prices = {
            "AAPL": Decimal("160.0"),
            "GOOG": Decimal("210.0"),
        }

        risk = analytics.calculate_portfolio_risk(positions, prices)

        # Gross = 8000 + 10500 = 18500
        # Equity = 10000 + unrealized
        # Leverage = gross / equity
        assert risk.current_leverage > Decimal("1")


class TestRiskAnalyticsLimits:
    """Tests for risk limit checking."""

    def test_check_limits_no_violations(self):
        """Test limit check with no violations."""
        analytics = RiskAnalytics(limits=RiskLimit())
        analytics.update_equity(Decimal("100000"))

        # Record some PnL history
        for _ in range(30):
            analytics.record_daily_pnl(Decimal("100"))

        positions = [{"symbol": "AAPL", "quantity": 10, "avg_price": 150.0}]
        prices = {"AAPL": Decimal("155.0")}

        risk = analytics.calculate_portfolio_risk(positions, prices)
        violations = analytics.check_limits(risk)

        # With small position, should have no violations
        assert len(violations) == 0

    def test_check_limits_var_violation(self):
        """Test VaR limit violation detection."""
        limits = RiskLimit(max_var_95_pct=0.01)  # 1% limit
        analytics = RiskAnalytics(limits=limits)
        analytics.update_equity(Decimal("10000"))

        # Record large losses to trigger VaR breach
        for _ in range(30):
            analytics.record_daily_pnl(Decimal("-500"))  # Big daily losses

        positions = [{"symbol": "AAPL", "quantity": 10, "avg_price": 100.0}]
        prices = {"AAPL": Decimal("100.0")}

        risk = analytics.calculate_portfolio_risk(positions, prices)
        violations = analytics.check_limits(risk)

        var_violations = [v for v in violations if "var" in v.limit_name]
        assert len(var_violations) > 0

    def test_check_limits_leverage_violation(self):
        """Test leverage limit violation detection."""
        limits = RiskLimit(max_leverage=1.5)
        analytics = RiskAnalytics(limits=limits)
        analytics.update_equity(Decimal("10000"))

        positions = [
            {"symbol": "AAPL", "quantity": 100, "avg_price": 150.0},
            {"symbol": "GOOG", "quantity": 100, "avg_price": 200.0},
        ]
        prices = {
            "AAPL": Decimal("160.0"),
            "GOOG": Decimal("210.0"),
        }

        risk = analytics.calculate_portfolio_risk(positions, prices)
        violations = analytics.check_limits(risk)

        lev_violations = [v for v in violations if v.limit_name == "max_leverage"]
        assert len(lev_violations) > 0

    def test_check_limits_exposure_violation(self):
        """Test gross exposure limit violation detection."""
        limits = RiskLimit(max_gross_exposure_pct=1.0)  # 100%
        analytics = RiskAnalytics(limits=limits)
        analytics.update_equity(Decimal("10000"))

        # Position worth 150% of equity
        positions = [{"symbol": "AAPL", "quantity": 100, "avg_price": 150.0}]
        prices = {"AAPL": Decimal("150.0")}

        risk = analytics.calculate_portfolio_risk(positions, prices)
        violations = analytics.check_limits(risk)

        exp_violations = [v for v in violations if "exposure" in v.limit_name]
        assert len(exp_violations) > 0


class TestRiskAnalyticsDailyPnL:
    """Tests for daily P&L recording."""

    def test_record_daily_pnl_growth(self):
        """Test daily PnL history grows correctly."""
        analytics = RiskAnalytics()

        analytics.record_daily_pnl(Decimal("100"))
        analytics.record_daily_pnl(Decimal("200"))
        analytics.record_daily_pnl(Decimal("-50"))

        assert len(analytics._daily_pnl_history) == 3
        assert analytics._daily_pnl_history == [100.0, 200.0, -50.0]

    def test_record_daily_pnl_limit(self):
        """Test daily PnL history is capped at 252 days."""
        analytics = RiskAnalytics()

        # Add 300 days of PnL
        for i in range(300):
            analytics.record_daily_pnl(Decimal(str(i)))

        # Should be capped at 252
        assert len(analytics._daily_pnl_history) == 252
        # Last entry should be from day 299 (0-indexed: 48-299)
        assert analytics._daily_pnl_history[-1] == 299.0


class TestRiskLimits:
    """Tests for RiskLimit dataclass."""

    def test_risk_limit_defaults(self):
        """Test default risk limit values."""
        limits = RiskLimit()

        assert limits.max_var_95_pct == 0.02
        assert limits.max_var_99_pct == 0.04
        assert limits.max_drawdown_pct == 0.10
        assert limits.max_leverage == 2.0
        assert limits.max_margin_utilization == 0.80

    def test_risk_limit_custom(self):
        """Test custom risk limit values."""
        limits = RiskLimit(
            max_var_95_pct=0.03,
            max_leverage=1.5,
        )

        assert limits.max_var_95_pct == 0.03
        assert limits.max_leverage == 1.5
        assert limits.max_drawdown_pct == 0.10  # Default


class TestRiskViolation:
    """Tests for RiskViolation dataclass."""

    def test_risk_violation_creation(self):
        """Test RiskViolation creation."""
        violation = RiskViolation(
            limit_name="max_var_95_pct",
            current_value=0.03,
            limit_value=0.02,
            severity="warning",
            message="VaR exceeds limit",
        )

        assert violation.limit_name == "max_var_95_pct"
        assert violation.current_value == 0.03
        assert violation.limit_value == 0.02
        assert violation.severity == "warning"
        assert violation.message == "VaR exceeds limit"
        assert violation.timestamp is not None


class TestRiskMetric:
    """Tests for RiskMetric enum."""

    def test_risk_metric_values(self):
        """Test RiskMetric enum values."""
        assert RiskMetric.VAR_95.value == "var_95"
        assert RiskMetric.VAR_99.value == "var_99"
        assert RiskMetric.CVAR.value == "cvar"
        assert RiskMetric.MAX_DRAWDOWN.value == "max_drawdown"
        assert RiskMetric.LEVERAGE.value == "leverage"
        assert RiskMetric.EXPOSURE.value == "exposure"
        assert RiskMetric.MARGIN_UTILIZATION.value == "margin_utilization"


class TestPositionRisk:
    """Tests for PositionRisk dataclass."""

    def test_position_risk_creation(self):
        """Test PositionRisk creation."""
        pos = PositionRisk(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_price=Decimal("150.0"),
            current_price=Decimal("160.0"),
            market_value=Decimal("16000"),
            unrealized_pnl=Decimal("1000"),
        )

        assert pos.symbol == "AAPL"
        assert pos.quantity == Decimal("100")
        assert pos.long_exposure == Decimal("0")  # Default
        assert pos.short_exposure == Decimal("0")  # Default


class TestPortfolioRisk:
    """Tests for PortfolioRisk dataclass."""

    def test_portfolio_risk_creation(self):
        """Test PortfolioRisk creation."""
        risk = PortfolioRisk(
            timestamp=datetime.now(timezone.utc),
            total_positions=5,
            long_positions=3,
            short_positions=2,
        )

        assert risk.total_positions == 5
        assert risk.long_positions == 3
        assert risk.short_positions == 2
        assert risk.current_leverage == Decimal("1")  # Default
