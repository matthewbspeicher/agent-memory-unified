import pytest
from decimal import Decimal
from datetime import datetime, date, timezone
from data.backtest import BacktestResult


class TestIsDeployable:
    def test_good_strategy_is_deployable(self):
        result = BacktestResult(
            agent_name="test", parameters={},
            sharpe_ratio=1.5, profit_factor=2.0, total_pnl=Decimal("5000"),
            max_drawdown=0.08, win_rate=0.6, total_trades=60,
            run_date=datetime.now(timezone.utc),
            data_start=date(2025, 1, 1), data_end=date(2025, 12, 31),
        )
        assert result.is_deployable(min_sharpe=1.0, min_trades=50) is True

    def test_low_sharpe_not_deployable(self):
        result = BacktestResult(
            agent_name="test", parameters={},
            sharpe_ratio=0.3, profit_factor=1.1, total_pnl=Decimal("500"),
            max_drawdown=0.15, win_rate=0.52, total_trades=100,
            run_date=datetime.now(timezone.utc),
            data_start=date(2025, 1, 1), data_end=date(2025, 12, 31),
        )
        assert result.is_deployable(min_sharpe=1.0, min_trades=50) is False

    def test_too_few_trades_not_deployable(self):
        result = BacktestResult(
            agent_name="test", parameters={},
            sharpe_ratio=2.0, profit_factor=3.0, total_pnl=Decimal("10000"),
            max_drawdown=0.05, win_rate=0.8, total_trades=10,
            run_date=datetime.now(timezone.utc),
            data_start=date(2025, 1, 1), data_end=date(2025, 12, 31),
        )
        assert result.is_deployable(min_sharpe=1.0, min_trades=50) is False

    def test_default_thresholds(self):
        result = BacktestResult(
            agent_name="test", parameters={},
            sharpe_ratio=1.1, profit_factor=1.5, total_pnl=Decimal("2000"),
            max_drawdown=0.10, win_rate=0.55, total_trades=55,
            run_date=datetime.now(timezone.utc),
            data_start=date(2025, 1, 1), data_end=date(2025, 12, 31),
        )
        # Default: min_sharpe=1.0, min_trades=50
        assert result.is_deployable() is True
