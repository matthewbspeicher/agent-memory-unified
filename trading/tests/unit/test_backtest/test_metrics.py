"""Per-trade backtest metrics (Sharpe, hit rate, drawdown)."""
from __future__ import annotations

import pytest

from backtest.metrics import compute_metrics


def test_compute_metrics_all_winners():
    trades = [
        {"pnl_cents": 5, "entry_ts": 1, "exit_ts": 2},
        {"pnl_cents": 3, "entry_ts": 2, "exit_ts": 3},
        {"pnl_cents": 7, "entry_ts": 3, "exit_ts": 4},
    ]
    m = compute_metrics(trades, starting_capital_cents=1000)
    assert m.hit_rate == pytest.approx(1.0)
    assert m.total_pnl_cents == 15
    assert m.max_drawdown_cents == 0
    assert m.num_trades == 3


def test_compute_metrics_mixed_with_drawdown():
    trades = [
        {"pnl_cents": 10, "entry_ts": 1, "exit_ts": 2},
        {"pnl_cents": -20, "entry_ts": 2, "exit_ts": 3},
        {"pnl_cents": 5, "entry_ts": 3, "exit_ts": 4},
    ]
    m = compute_metrics(trades, starting_capital_cents=1000)
    assert m.hit_rate == pytest.approx(2 / 3)
    assert m.total_pnl_cents == -5
    # Equity: 1000 → 1010 → 990 → 995; peak 1010, trough 990 → DD 20
    assert m.max_drawdown_cents == 20


def test_compute_metrics_empty_trades():
    m = compute_metrics([], starting_capital_cents=1000)
    assert m.hit_rate == 0.0
    assert m.total_pnl_cents == 0
    assert m.sharpe is None
    assert m.max_drawdown_cents == 0
    assert m.num_trades == 0


def test_compute_metrics_single_trade_sharpe_none():
    # One sample can't produce a stdev; Sharpe undefined.
    trades = [{"pnl_cents": 10, "entry_ts": 1, "exit_ts": 2}]
    m = compute_metrics(trades, starting_capital_cents=1000)
    assert m.sharpe is None
    assert m.num_trades == 1


def test_compute_metrics_zero_variance_sharpe_none():
    # Identical P&Ls → stdev 0 → Sharpe undefined, not infinity.
    trades = [
        {"pnl_cents": 5, "entry_ts": 1, "exit_ts": 2},
        {"pnl_cents": 5, "entry_ts": 2, "exit_ts": 3},
        {"pnl_cents": 5, "entry_ts": 3, "exit_ts": 4},
    ]
    m = compute_metrics(trades, starting_capital_cents=1000)
    assert m.sharpe is None
