"""Per-trade backtest metrics for prediction-market strategies.

Separate from ``backtest.engine`` which uses daily-return semantics for
synthetic crypto/equity backtests. Prediction-market strategies settle
per-trade on resolution, so Sharpe is computed on per-trade P&L rather
than a daily equity curve.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class BacktestMetrics:
    total_pnl_cents: int
    hit_rate: float
    sharpe: float | None
    max_drawdown_cents: int
    num_trades: int


def compute_metrics(
    trades: Iterable[dict], starting_capital_cents: int
) -> BacktestMetrics:
    trades = list(trades)
    if not trades:
        return BacktestMetrics(
            total_pnl_cents=0,
            hit_rate=0.0,
            sharpe=None,
            max_drawdown_cents=0,
            num_trades=0,
        )

    pnls = [int(t["pnl_cents"]) for t in trades]
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    hit_rate = wins / len(pnls)

    if len(pnls) > 1:
        mean = sum(pnls) / len(pnls)
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        stdev = math.sqrt(var)
        sharpe = mean / stdev if stdev > 0 else None
    else:
        sharpe = None

    equity = starting_capital_cents
    peak = equity
    max_dd = 0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    return BacktestMetrics(
        total_pnl_cents=total,
        hit_rate=hit_rate,
        sharpe=sharpe,
        max_drawdown_cents=max_dd,
        num_trades=len(pnls),
    )
