#!/usr/bin/env python3
"""Backtest runner for arb strategy using 30 days of SpreadStore history."""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

sys.path.insert(0, str(Path(__file__).parent.parent / "trading"))

from execution.cost_model import CostModel
from storage.spreads import SpreadStore


@dataclass
class BacktestTrade:
    timestamp: str
    kalshi_ticker: str
    poly_ticker: str
    gap_cents: float
    gross_profit_bps: float
    fees_bps: float
    net_profit_bps: float
    quantity: int
    notional_usd: float


@dataclass
class BacktestResult:
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl_usd: float
    total_pnl_bps: float
    avg_profit_bps: float
    max_drawdown_pct: float
    sharpe_ratio: float
    recommendation: str
    trades: list[BacktestTrade]


async def load_spread_history(db_path: str, days: int = 30) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        store = SpreadStore(db)
        cursor = await db.execute(
            "SELECT DISTINCT kalshi_ticker, poly_ticker FROM arb_spread_observations"
        )
        pairs = await cursor.fetchall()

        all_observations = []
        for kalshi_ticker, poly_ticker in pairs:
            history = await store.get_history(
                kalshi_ticker, poly_ticker, hours=days * 24
            )
            for obs in history:
                all_observations.append(
                    {
                        "timestamp": obs.observed_at,
                        "kalshi_ticker": obs.kalshi_ticker,
                        "poly_ticker": obs.poly_ticker,
                        "gap_cents": obs.gap_cents,
                        "kalshi_cents": obs.kalshi_cents,
                        "poly_cents": obs.poly_cents,
                    }
                )

        all_observations.sort(key=lambda x: x["timestamp"])
        return all_observations


def run_backtest(
    observations: list[dict],
    min_profit_bps: float = 5.0,
    position_size_usd: float = 100.0,
) -> BacktestResult:
    cost_model = CostModel()
    trades: list[BacktestTrade] = []
    equity_curve: list[float] = [0.0]

    for obs in observations:
        gap_cents = obs["gap_cents"]

        if not cost_model.should_execute(gap_cents, min_profit_bps):
            continue

        breakdown = cost_model.calculate_breakdown(gap_cents)
        quantity = int(position_size_usd / 100)
        notional = position_size_usd

        trade = BacktestTrade(
            timestamp=obs["timestamp"],
            kalshi_ticker=obs["kalshi_ticker"],
            poly_ticker=obs["poly_ticker"],
            gap_cents=gap_cents,
            gross_profit_bps=float(breakdown.gross_gap_bps),
            fees_bps=float(breakdown.total_fee_bps),
            net_profit_bps=float(breakdown.net_profit_bps),
            quantity=quantity,
            notional_usd=notional,
        )
        trades.append(trade)

        pnl = notional * float(breakdown.net_profit_bps) / 10000
        equity_curve.append(equity_curve[-1] + pnl)

    if not trades:
        return BacktestResult(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            total_pnl_usd=0.0,
            total_pnl_bps=0.0,
            avg_profit_bps=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
            recommendation="KILL",
            trades=[],
        )

    winning = sum(1 for t in trades if t.net_profit_bps > 0)
    losing = len(trades) - winning
    total_pnl = equity_curve[-1]
    avg_profit = sum(t.net_profit_bps for t in trades) / len(trades)

    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / abs(peak) if peak != 0 else 0
        if dd > max_dd:
            max_dd = dd

    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] != 0:
            ret = (equity_curve[i] - equity_curve[i - 1]) / position_size_usd
            returns.append(ret)

    if returns and len(returns) > 1:
        import statistics

        mean_return = statistics.mean(returns)
        std_return = statistics.stdev(returns) if len(returns) > 1 else 0.001
        sharpe = (mean_return / std_return) * (252**0.5) if std_return > 0 else 0.0
    else:
        sharpe = 0.0

    recommendation = "GO" if sharpe >= 1.0 and max_dd <= 0.15 else "KILL"

    return BacktestResult(
        total_trades=len(trades),
        winning_trades=winning,
        losing_trades=losing,
        total_pnl_usd=total_pnl,
        total_pnl_bps=sum(t.net_profit_bps for t in trades),
        avg_profit_bps=avg_profit,
        max_drawdown_pct=max_dd * 100,
        sharpe_ratio=sharpe,
        recommendation=recommendation,
        trades=trades,
    )


def generate_report(
    result: BacktestResult, output_dir: Path, days: int
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    csv_path = output_dir / f"arb-trades-{date_str}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "timestamp",
                "kalshi_ticker",
                "poly_ticker",
                "gap_cents",
                "gross_profit_bps",
                "fees_bps",
                "net_profit_bps",
                "quantity",
                "notional_usd",
            ]
        )
        for trade in result.trades:
            writer.writerow(
                [
                    trade.timestamp,
                    trade.kalshi_ticker,
                    trade.poly_ticker,
                    trade.gap_cents,
                    trade.gross_profit_bps,
                    trade.fees_bps,
                    trade.net_profit_bps,
                    trade.quantity,
                    trade.notional_usd,
                ]
            )

    md_path = output_dir / f"arb-{date_str}.md"
    win_pct = (
        result.winning_trades / result.total_trades * 100
        if result.total_trades > 0
        else 0
    )
    with open(md_path, "w") as f:
        f.write(f"""# Arbitrage Strategy Backtest Report

**Generated**: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
**Period**: {days} days
**Recommendation**: {"GO" if result.recommendation == "GO" else "KILL"}

## Summary

| Metric | Value |
|--------|-------|
| Total Trades | {result.total_trades} |
| Winning Trades | {result.winning_trades} ({win_pct:.1f}%) |
| Losing Trades | {result.losing_trades} |
| Total P&L | ${result.total_pnl_usd:.2f} |
| Avg Profit (bps) | {result.avg_profit_bps:.2f} |
| Max Drawdown | {result.max_drawdown_pct:.2f}% |
| Sharpe Ratio | {result.sharpe_ratio:.3f} |

## Kill/Go Criteria

| Criterion | Threshold | Actual | Status |
|-----------|-----------|--------|--------|
| Sharpe Ratio | >= 1.0 | {result.sharpe_ratio:.3f} | {"PASS" if result.sharpe_ratio >= 1.0 else "FAIL"} |
| Max Drawdown | <= 15% | {result.max_drawdown_pct:.2f}% | {"PASS" if result.max_drawdown_pct <= 15 else "FAIL"} |

## Recommendation

**{result.recommendation}** - {"Strategy meets criteria for live deployment." if result.recommendation == "GO" else "Strategy does not meet criteria. Do not deploy."}

## Trade Log

See attached CSV: `arb-trades-{date_str}.csv`

Top 10 trades by profit:
""")

        sorted_trades = sorted(
            result.trades, key=lambda t: t.net_profit_bps, reverse=True
        )[:10]
        f.write("| # | Timestamp | Pair | Gap (cents) | Net (bps) | P&L ($) |\n")
        f.write("|---|-----------|------|-------------|-----------|--------|\n")
        for i, trade in enumerate(sorted_trades, 1):
            pnl = trade.notional_usd * trade.net_profit_bps / 10000
            f.write(
                f"| {i} | {trade.timestamp[:19]} | {trade.kalshi_ticker}/{trade.poly_ticker} | {trade.gap_cents:.1f} | {trade.net_profit_bps:.1f} | ${pnl:.2f} |\n"
            )

    return md_path, csv_path


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--min-profit-bps", type=float, default=5.0)
    parser.add_argument("--position-size", type=float, default=100.0)
    parser.add_argument("--db", type=str, default="trading/data/spreads.db")
    parser.add_argument("--output", type=str, default="docs/backtests")

    args = parser.parse_args()

    print(f"Loading {args.days} days of spread history from {args.db}...")
    observations = await load_spread_history(args.db, args.days)
    print(f"Loaded {len(observations)} observations")

    if not observations:
        print("No observations found. Exiting.")
        return

    print(f"Running backtest with min_profit_bps={args.min_profit_bps}...")
    result = run_backtest(observations, args.min_profit_bps, args.position_size)

    print(f"\nBacktest Results ({args.days} days)")
    print(f"Total Trades: {result.total_trades}")
    if result.total_trades > 0:
        print(f"Win Rate: {result.winning_trades / result.total_trades * 100:.1f}%")
    print(f"Total P&L: ${result.total_pnl_usd:.2f}")
    print(f"Avg Profit: {result.avg_profit_bps:.2f} bps")
    print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
    print(f"Sharpe Ratio: {result.sharpe_ratio:.3f}")
    print(f"\nRecommendation: {result.recommendation}\n")

    output_dir = Path(args.output)
    md_path, csv_path = generate_report(result, output_dir, args.days)
    print(f"Report written to: {md_path}")
    print(f"Trades CSV: {csv_path}")


if __name__ == "__main__":
    asyncio.run(main())
