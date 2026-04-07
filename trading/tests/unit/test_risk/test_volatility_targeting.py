"""Tests for VolatilityTargeter position sizing module."""

import math

import pytest

from risk.volatility_targeting import VolatilityTarget, VolatilityTargeter


class TestVolatilityTargeter:
    """Test volatility-based position sizing."""

    def setup_method(self):
        self.targeter = VolatilityTargeter(
            target_vol=0.15,
            lookback_days=20,
            min_scalar=0.25,
            max_scalar=2.0,
            annualize_factor=365.0,
        )

    def _make_returns(self, daily_vol: float, n: int = 30) -> list[float]:
        """Generate synthetic returns with a known daily volatility.

        Uses an alternating +/- pattern so std dev equals daily_vol exactly.
        """
        return [daily_vol if i % 2 == 0 else -daily_vol for i in range(n)]

    # ------------------------------------------------------------------
    # Core sizing tests
    # ------------------------------------------------------------------

    def test_high_vol_reduces_size(self):
        """30% realized vol with 15% target -> size roughly halved."""
        # daily vol that annualizes to ~30%
        daily_vol = 0.30 / math.sqrt(365.0)
        returns = self._make_returns(daily_vol, n=30)

        result = self.targeter.compute(returns, raw_size=1.0)

        assert isinstance(result, VolatilityTarget)
        assert result.adjusted_size < result.raw_size
        assert result.vol_scalar == pytest.approx(0.5, abs=0.05)
        assert result.adjusted_size == pytest.approx(0.5, abs=0.05)

    def test_low_vol_increases_size(self):
        """7.5% realized vol with 15% target -> size roughly doubled."""
        daily_vol = 0.075 / math.sqrt(365.0)
        returns = self._make_returns(daily_vol, n=30)

        result = self.targeter.compute(returns, raw_size=1.0)

        assert result.adjusted_size > result.raw_size
        assert result.vol_scalar == pytest.approx(2.0, abs=0.1)
        assert result.adjusted_size == pytest.approx(2.0, abs=0.1)

    def test_scalar_clamped_at_max(self):
        """Very low vol should not exceed max_scalar."""
        daily_vol = 0.01 / math.sqrt(365.0)  # ~1% annualized
        returns = self._make_returns(daily_vol, n=30)

        result = self.targeter.compute(returns, raw_size=1.0)

        assert result.vol_scalar == 2.0
        assert result.adjusted_size == 2.0

    def test_scalar_clamped_at_min(self):
        """Very high vol should not go below min_scalar."""
        daily_vol = 1.0 / math.sqrt(365.0)  # ~100% annualized
        returns = self._make_returns(daily_vol, n=30)

        result = self.targeter.compute(returns, raw_size=1.0)

        assert result.vol_scalar == 0.25
        assert result.adjusted_size == 0.25

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_zero_vol_returns_raw_size(self):
        """Zero volatility should return raw_size unchanged."""
        returns = [0.0] * 30

        result = self.targeter.compute(returns, raw_size=5.0)

        assert result.adjusted_size == 5.0
        assert result.realized_vol == 0.0
        assert result.vol_scalar == 1.0

    def test_short_history_still_works(self):
        """Fewer than lookback_days returns should still compute."""
        daily_vol = 0.15 / math.sqrt(365.0)
        returns = self._make_returns(daily_vol, n=5)  # only 5, lookback=20

        result = self.targeter.compute(returns, raw_size=1.0)

        # Should still produce a valid result
        assert isinstance(result, VolatilityTarget)
        assert result.adjusted_size > 0
        assert result.realized_vol > 0

    # ------------------------------------------------------------------
    # Static method
    # ------------------------------------------------------------------

    def test_realized_volatility_calculation(self):
        """Verify annualized vol math: sample_std(returns) * sqrt(annualize)."""
        daily_vol = 0.01  # 1% daily
        n = 20
        returns = self._make_returns(daily_vol, n=n)

        vol = VolatilityTargeter.realized_volatility(returns, lookback=n, annualize=365.0)

        # Sample std dev uses n-1 (Bessel's correction):
        # For alternating +/- v with mean=0: sample_std = v * sqrt(n / (n-1))
        sample_std = daily_vol * math.sqrt(n / (n - 1))
        expected = sample_std * math.sqrt(365.0)
        assert vol == pytest.approx(expected, rel=0.01)

    # ------------------------------------------------------------------
    # Regime passthrough
    # ------------------------------------------------------------------

    def test_regime_passed_through(self):
        """Regime label should be stored in the result."""
        daily_vol = 0.15 / math.sqrt(365.0)
        returns = self._make_returns(daily_vol, n=30)

        result = self.targeter.compute(returns, raw_size=1.0, regime="high_volatility")

        assert result.regime == "high_volatility"

    def test_regime_none_by_default(self):
        """Regime should be None if not provided."""
        daily_vol = 0.15 / math.sqrt(365.0)
        returns = self._make_returns(daily_vol, n=30)

        result = self.targeter.compute(returns, raw_size=1.0)

        assert result.regime is None
