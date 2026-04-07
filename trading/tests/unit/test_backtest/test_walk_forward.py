"""Tests for WalkForwardEngine — rolling train/test window backtesting."""

import numpy as np
import pytest
from datetime import datetime, timedelta, timezone

from backtesting.walk_forward import WalkForwardEngine, WindowResult, WalkForwardResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    """Default walk-forward engine (30d train, 7d test, 7d step)."""
    return WalkForwardEngine(
        train_days=30,
        test_days=7,
        step_days=7,
        min_trades_per_window=5,
        overfit_threshold=2.0,
    )


@pytest.fixture
def start_end():
    """90-day date range."""
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 4, 1, tzinfo=timezone.utc)  # 90 days
    return start, end


@pytest.fixture
def synthetic_returns_100():
    """100 days of synthetic returns with slight positive drift."""
    rng = np.random.default_rng(42)
    returns = rng.normal(loc=0.001, scale=0.02, size=100).tolist()
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    timestamps = [start + timedelta(days=i) for i in range(100)]
    return returns, timestamps


# ---------------------------------------------------------------------------
# Window generation tests
# ---------------------------------------------------------------------------

class TestGenerateWindows:

    def test_generate_windows_correct_count(self, engine, start_end):
        """90 days with 30/7/7 → windows fit until test_end <= end."""
        start, end = start_end
        windows = engine.generate_windows(start, end)
        # First window: train 0-30, test 30-37 → day 37
        # Each step adds 7 days to the start
        # Window n starts at day 7*n, train ends at 7*n+30, test ends at 7*n+37
        # Need 7*n+37 <= 90 → n <= (90-37)/7 = 7.57 → n=0..7 → 8 windows
        assert len(windows) == 8

    def test_generate_windows_no_overlap_in_test(self, engine, start_end):
        """Test periods should not overlap with the *next* window's test period
        (they can overlap with next window's train — that's expected in walk-forward)."""
        start, end = start_end
        windows = engine.generate_windows(start, end)
        assert len(windows) >= 2

        for i in range(len(windows) - 1):
            train_start_i, train_end_i, test_start_i, test_end_i = windows[i]
            train_start_next, train_end_next, test_start_next, test_end_next = windows[i + 1]

            # Train end == test start within a window
            assert train_end_i == test_start_i
            # test_end of window i should be <= test_start of window i+1
            # (no test-period overlap)
            assert test_end_i <= test_start_next

    def test_generate_windows_returns_tuples(self, engine, start_end):
        start, end = start_end
        windows = engine.generate_windows(start, end)
        for w in windows:
            assert len(w) == 4
            train_start, train_end, test_start, test_end = w
            assert train_start < train_end
            assert test_start < test_end
            assert train_end == test_start


# ---------------------------------------------------------------------------
# Static method tests
# ---------------------------------------------------------------------------

class TestSharpeRatio:

    def test_sharpe_ratio_positive(self):
        """Known positive returns should yield positive Sharpe."""
        returns = [0.01] * 30 + [0.005] * 30  # consistently positive
        sharpe = WalkForwardEngine.sharpe_ratio(returns)
        assert sharpe > 0

    def test_sharpe_ratio_zero_std(self):
        """Constant returns → std=0 → Sharpe should be 0."""
        returns = [0.01] * 50
        sharpe = WalkForwardEngine.sharpe_ratio(returns)
        assert sharpe == 0.0

    def test_sharpe_ratio_empty(self):
        """Empty or single-element returns → 0."""
        assert WalkForwardEngine.sharpe_ratio([]) == 0.0
        assert WalkForwardEngine.sharpe_ratio([0.01]) == 0.0

    def test_sharpe_ratio_negative(self):
        """Consistently negative returns → negative Sharpe."""
        returns = [-0.02, -0.01, -0.015, -0.03, -0.01]
        sharpe = WalkForwardEngine.sharpe_ratio(returns)
        assert sharpe < 0


class TestMaxDrawdown:

    def test_max_drawdown_calculation(self):
        """Known drawdown scenario: go up then crash."""
        # +10%, +10%, -30%, +5% → peak at 1.21, drop to 0.847, dd ≈ -30%
        returns = [0.10, 0.10, -0.30, 0.05]
        dd = WalkForwardEngine.max_drawdown(returns)
        assert dd < 0  # drawdown is negative
        assert dd == pytest.approx(-0.30, abs=0.01)

    def test_max_drawdown_no_drawdown(self):
        """Monotonically increasing returns → drawdown is 0."""
        returns = [0.01, 0.02, 0.03, 0.01]
        dd = WalkForwardEngine.max_drawdown(returns)
        assert dd == pytest.approx(0.0, abs=1e-10)

    def test_max_drawdown_empty(self):
        """Empty returns → 0."""
        assert WalkForwardEngine.max_drawdown([]) == 0.0


# ---------------------------------------------------------------------------
# Window evaluation tests
# ---------------------------------------------------------------------------

class TestEvaluateWindow:

    def test_evaluate_window_detects_overfit(self):
        """High train Sharpe + low test Sharpe → is_overfit=True."""
        engine = WalkForwardEngine(overfit_threshold=2.0)

        # Train: strong positive returns (high Sharpe)
        rng = np.random.default_rng(42)
        train_returns = (rng.normal(loc=0.02, scale=0.005, size=30)).tolist()
        # Test: weak positive returns (low Sharpe)
        test_returns = (rng.normal(loc=0.001, scale=0.02, size=7)).tolist()

        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        result = engine.evaluate_window(
            returns_train=train_returns,
            returns_test=test_returns,
            train_start=now,
            train_end=now + timedelta(days=30),
            test_start=now + timedelta(days=30),
            test_end=now + timedelta(days=37),
        )

        assert isinstance(result, WindowResult)
        assert result.train_sharpe > 0
        assert result.is_overfit is True  # train >> test

    def test_evaluate_window_not_overfit(self):
        """Similar train/test Sharpe → is_overfit=False."""
        engine = WalkForwardEngine(overfit_threshold=2.0)

        rng = np.random.default_rng(99)
        # Both periods: similar distribution
        train_returns = rng.normal(loc=0.005, scale=0.01, size=30).tolist()
        test_returns = rng.normal(loc=0.005, scale=0.01, size=7).tolist()

        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        result = engine.evaluate_window(
            returns_train=train_returns,
            returns_test=test_returns,
            train_start=now,
            train_end=now + timedelta(days=30),
            test_start=now + timedelta(days=30),
            test_end=now + timedelta(days=37),
        )

        assert result.is_overfit is False


# ---------------------------------------------------------------------------
# Full walk-forward run tests
# ---------------------------------------------------------------------------

class TestRun:

    def test_run_full_walk_forward(self, synthetic_returns_100):
        """Run walk-forward on 100 days of synthetic data."""
        returns, timestamps = synthetic_returns_100
        engine = WalkForwardEngine(
            train_days=30,
            test_days=7,
            step_days=7,
            min_trades_per_window=0,  # no trade count filtering for returns-only test
        )

        result = engine.run(daily_returns=returns, timestamps=timestamps)

        assert isinstance(result, WalkForwardResult)
        assert len(result.windows) > 0
        # With 100 days, 30+7 train+test, step 7: should get several windows
        assert len(result.windows) >= 5
        assert isinstance(result.avg_test_sharpe, float)
        assert isinstance(result.avg_test_return, float)
        assert isinstance(result.avg_test_max_drawdown, float)
        assert isinstance(result.total_test_trades, int)

    def test_walk_forward_efficiency(self, synthetic_returns_100):
        """Walk-forward efficiency should be a finite ratio."""
        returns, timestamps = synthetic_returns_100
        engine = WalkForwardEngine(
            train_days=30, test_days=7, step_days=7, min_trades_per_window=0
        )
        result = engine.run(daily_returns=returns, timestamps=timestamps)

        assert isinstance(result.walk_forward_efficiency, float)
        # Should be a reasonable value (not inf/nan)
        assert np.isfinite(result.walk_forward_efficiency)

    def test_overfit_ratio(self):
        """Verify overfit_ratio counts overfit windows correctly."""
        # Create data where train periods have very high returns but
        # test periods are near zero → should trigger overfit detection
        rng = np.random.default_rng(123)
        n = 100
        returns = []
        for i in range(n):
            # In "train" regions (first 30 of each 37-day block), high returns
            # In "test" regions, low/noisy returns
            cycle_pos = i % 37
            if cycle_pos < 30:
                returns.append(0.03 + rng.normal(0, 0.002))
            else:
                returns.append(rng.normal(0.0, 0.02))

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        timestamps = [start + timedelta(days=i) for i in range(n)]

        engine = WalkForwardEngine(
            train_days=30, test_days=7, step_days=7,
            min_trades_per_window=0, overfit_threshold=2.0,
        )
        result = engine.run(daily_returns=returns, timestamps=timestamps)

        assert isinstance(result.overfit_ratio, float)
        assert 0.0 <= result.overfit_ratio <= 1.0
        # With the structured data above, at least some windows should be overfit
        assert result.overfit_ratio > 0.0

    def test_empty_returns_handles_gracefully(self):
        """Empty returns → graceful result with zero windows."""
        engine = WalkForwardEngine()
        result = engine.run(daily_returns=[], timestamps=[])

        assert isinstance(result, WalkForwardResult)
        assert len(result.windows) == 0
        assert result.avg_test_sharpe == 0.0
        assert result.avg_test_return == 0.0
        assert result.overfit_ratio == 0.0
        assert result.walk_forward_efficiency == 0.0

    def test_insufficient_data_handles_gracefully(self):
        """Data shorter than one window → zero windows."""
        engine = WalkForwardEngine(train_days=30, test_days=7)
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        returns = [0.01] * 10
        timestamps = [start + timedelta(days=i) for i in range(10)]

        result = engine.run(daily_returns=returns, timestamps=timestamps)
        assert len(result.windows) == 0
