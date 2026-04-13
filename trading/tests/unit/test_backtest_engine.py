"""Tests for backtest.engine — the importable backtest library."""

import pytest
from backtest.engine import run_backtest


class TestRunBacktest:
    def test_returns_required_fields(self):
        result = run_backtest(symbols=["BTC"], days=30)
        assert "sharpe_ratio" in result
        assert "win_rate" in result
        assert "max_drawdown" in result
        assert "total_trades" in result
        assert "equity_curve" in result
        assert "status" in result

    def test_status_is_real(self):
        result = run_backtest(symbols=["BTC"], days=30)
        assert result["status"] == "real"

    def test_equity_curve_has_correct_length(self):
        result = run_backtest(symbols=["BTC"], days=60)
        assert len(result["equity_curve"]) == 60

    def test_equity_curve_entries_have_timestamp_and_equity(self):
        result = run_backtest(symbols=["ETH"], days=10)
        for point in result["equity_curve"]:
            assert "timestamp" in point
            assert "equity" in point
            assert isinstance(point["equity"], float)

    def test_initial_capital_respected(self):
        result = run_backtest(symbols=["BTC"], days=10, initial_capital=50_000)
        assert result["initial_capital"] == 50_000

    def test_max_drawdown_is_negative_or_zero(self):
        result = run_backtest(symbols=["BTC"], days=30)
        assert result["max_drawdown"] <= 0

    def test_win_rate_between_zero_and_one(self):
        result = run_backtest(symbols=["BTC", "ETH"], days=60)
        assert 0 <= result["win_rate"] <= 1

    def test_multiple_symbols(self):
        result = run_backtest(symbols=["BTC", "ETH", "SOL"], days=30)
        assert result["total_trades"] >= 0

    def test_custom_regime_weights(self):
        custom = {
            "trending": {"technical": 0.5, "sentiment": 0.2, "whale": 0.1, "momentum": 0.2},
            "ranging": {"technical": 0.3, "sentiment": 0.3, "whale": 0.2, "momentum": 0.2},
            "volatile": {"technical": 0.2, "sentiment": 0.3, "whale": 0.3, "momentum": 0.2},
        }
        result = run_backtest(symbols=["BTC"], days=30, regime_weights=custom)
        assert result["status"] == "real"

    def test_defaults_work(self):
        result = run_backtest()
        assert result["status"] == "real"
        assert len(result["equity_curve"]) == 90  # default days
