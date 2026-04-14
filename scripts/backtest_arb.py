#!/usr/bin/env python3
"""Backtest runner for Kalshi↔Polymarket arb using SpreadStore history.

Usage:
    python scripts/backtest_arb.py --db /tmp/spreads.db --days 30

The script is intentionally strict about data sufficiency:
- Exits 1 with an explanation if the SpreadStore has zero observations.
- Exits 1 if the history covers < 50% of the requested days.
- Emits a KILL or GO recommendation only when sufficient data is present.

Idempotent: given the same db snapshot, two runs produce identical output
to the same datestamped path.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiosqlite

sys.path.insert(0, str(Path(__file__).parent.parent / "trading"))

from execution.cost_model import CostModel  # noqa: E402


@dataclass
class BacktestTrade:
    timestamp: str
    kalshi_ticker: str
    poly_ticker: str
    gap_cents: float
    gross_profit_bps: float
    fees_bps: float
    slippage_bps: float
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
    recommendation_reason: str
    trades: list[BacktestTrade]
    observations_count: int
    coverage_days: float
    coverage_requested_days: int


async def load_spread_history(db_path: str, days: int) -> list[dict]:
    """Load all spread observations from the SQLite SpreadStore db."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = await db.execute(
            """SELECT kalshi_ticker, poly_ticker, match_score,
                      kalshi_cents, poly_cents, gap_cents,
                      kalshi_volume, poly_volume, observed_at
               FROM arb_spread_observations
               WHERE observed_at >= ?
               ORDER BY observed_at ASC""",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


def compute_coverage_days(observations: list[dict]) -> float:
    """How many days of data the observations actually span."""
    if not observations:
        return 0.0
    try:
        first = datetime.fromisoformat(observations[0]["observed_at"])
        last = datetime.fromisoformat(observations[-1]["observed_at"])
    except (KeyError, ValueError):
        return 0.0
    return (last - first).total_seconds() / 86400.0


def run_backtest(
    observations: list[dict],
    requested_days: int,
    min_profit_bps: float = 5.0,
    position_size_usd: float = 100.0,
) -> BacktestResult:
    cost_model = CostModel()
    trades: list[BacktestTrade] = []
    equity_curve: list[float] = [0.0]
    coverage = compute_coverage_days(observations)

    for obs in observations:
        gap_cents = obs["gap_cents"]

        if not cost_model.should_execute(gap_cents, min_profit_bps):
            continue

        breakdown = cost_model.calculate_breakdown(gap_cents)
        quantity = max(int(position_size_usd / 100), 1)
        notional = position_size_usd

        trade = BacktestTrade(
            timestamp=obs["observed_at"],
            kalshi_ticker=obs["kalshi_ticker"],
            poly_ticker=obs["poly_ticker"],
            gap_cents=float(gap_cents),
            gross_profit_bps=float(breakdown.gross_gap_bps),
            fees_bps=float(breakdown.total_fee_bps),
            slippage_bps=float(breakdown.slippage_bps),
            net_profit_bps=float(breakdown.net_profit_bps),
            quantity=quantity,
            notional_usd=notional,
        )
        trades.append(trade)

        pnl = notional * float(breakdown.net_profit_bps) / 10000
        equity_curve.append(equity_curve[-1] + pnl)

    # Recommendation logic — honest about data sufficiency.
    coverage_sufficient = coverage >= (requested_days * 0.5)

    if not observations:
        return BacktestResult(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            total_pnl_usd=0.0,
            total_pnl_bps=0.0,
            avg_profit_bps=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
            recommendation="INSUFFICIENT_DATA",
            recommendation_reason=(
                f"Zero spread observations in the last {requested_days} days. "
                "This is not a strategy kill signal — it is a data-collection "
                "gap. Investigate why cross_platform_arb / spread_tracker are "
                "not writing to arb_spread_observations before re-running."
            ),
            trades=[],
            observations_count=0,
            coverage_days=0.0,
            coverage_requested_days=requested_days,
        )

    if not coverage_sufficient:
        return BacktestResult(
            total_trades=len(trades),
            winning_trades=0,
            losing_trades=0,
            total_pnl_usd=equity_curve[-1],
            total_pnl_bps=0.0,
            avg_profit_bps=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
            recommendation="INSUFFICIENT_DATA",
            recommendation_reason=(
                f"Data covers only {coverage:.1f} of the requested "
                f"{requested_days} days (<50%). Sharpe is not meaningful on "
                "this sample. Collect more history and re-run."
            ),
            trades=trades,
            observations_count=len(observations),
            coverage_days=coverage,
            coverage_requested_days=requested_days,
        )

    winning = sum(1 for t in trades if t.net_profit_bps > 0)
    losing = len(trades) - winning
    total_pnl = equity_curve[-1]
    avg_profit = sum(t.net_profit_bps for t in trades) / len(trades) if trades else 0.0

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
        ret = (equity_curve[i] - equity_curve[i - 1]) / position_size_usd
        returns.append(ret)

    if len(returns) > 1:
        import statistics

        mean_return = statistics.mean(returns)
        std_return = statistics.stdev(returns)
        sharpe = (mean_return / std_return) * (252**0.5) if std_return > 0 else 0.0
    else:
        sharpe = 0.0

    if not trades:
        recommendation = "KILL"
        reason = (
            f"{len(observations)} observations covering {coverage:.1f} days, "
            "but zero met the cost-adjusted profit threshold. "
            "Strategy does not clear fees + default slippage."
        )
    elif sharpe >= 1.0 and max_dd <= 0.15:
        recommendation = "GO"
        reason = (
            f"Sharpe {sharpe:.2f} ≥ 1.0 and max DD {max_dd * 100:.1f}% ≤ 15%. "
            "Meets gate."
        )
    else:
        recommendation = "KILL"
        reason = (
            f"Sharpe {sharpe:.2f} (need ≥ 1.0) or max DD {max_dd * 100:.1f}% "
            "(need ≤ 15%) fail the gate."
        )

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
        recommendation_reason=reason,
        trades=trades,
        observations_count=len(observations),
        coverage_days=coverage,
        coverage_requested_days=requested_days,
    )


def generate_report(
    result: BacktestResult,
    output_dir: Path,
    db_path: str,
    min_profit_bps: float,
    position_size_usd: float,
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
                "slippage_bps",
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
                    trade.slippage_bps,
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

**Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
**Source db:** `{db_path}`
**Requested window:** {result.coverage_requested_days} days
**Actual coverage:** {result.coverage_days:.2f} days ({result.observations_count} observations)
**Min profit threshold:** {min_profit_bps} bps (after fees + default slippage)
**Position size:** ${position_size_usd}

## Recommendation

**{result.recommendation}**

{result.recommendation_reason}

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
| Observations > 0 | yes | {result.observations_count} | {"PASS" if result.observations_count > 0 else "FAIL"} |
| Coverage ≥ 50% of requested | ≥ {result.coverage_requested_days * 0.5:.1f}d | {result.coverage_days:.2f}d | {"PASS" if result.coverage_days >= result.coverage_requested_days * 0.5 else "FAIL"} |
| Sharpe Ratio | ≥ 1.0 | {result.sharpe_ratio:.3f} | {"PASS" if result.sharpe_ratio >= 1.0 else "FAIL"} |
| Max Drawdown | ≤ 15% | {result.max_drawdown_pct:.2f}% | {"PASS" if result.max_drawdown_pct <= 15 else "FAIL"} |

## Notes on slippage

All trades in this report use the `CostModel` default slippage
({float(CostModel().min_gap_cents()) * 100 - 400:.0f} bps) because `SpreadStore` observations do not
currently capture orderbook depth. Any trade row shows
`slippage_bps` reflecting this default. To improve accuracy, add an
orderbook-snapshot column to `arb_spread_observations` and pipe it
through `calculate_breakdown(..., slippage_bps=...)`.

## Trade log

Full CSV: `arb-trades-{date_str}.csv`
""")

        if result.trades:
            f.write("\nTop 10 trades by net profit:\n\n")
            sorted_trades = sorted(
                result.trades, key=lambda t: t.net_profit_bps, reverse=True
            )[:10]
            f.write("| # | Timestamp | Pair | Gap (cents) | Net (bps) | P&L ($) |\n")
            f.write("|---|-----------|------|-------------|-----------|---------|\n")
            for i, trade in enumerate(sorted_trades, 1):
                pnl = trade.notional_usd * trade.net_profit_bps / 10000
                f.write(
                    f"| {i} | {trade.timestamp[:19]} | "
                    f"{trade.kalshi_ticker}/{trade.poly_ticker} | "
                    f"{trade.gap_cents:.1f} | {trade.net_profit_bps:.1f} | "
                    f"${pnl:.2f} |\n"
                )
        else:
            f.write("\n_No trades met the execution threshold._\n")

    return md_path, csv_path


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--min-profit-bps", type=float, default=5.0)
    parser.add_argument("--position-size", type=float, default=100.0)
    parser.add_argument(
        "--db",
        type=str,
        required=True,
        help="Path to the SpreadStore SQLite file (e.g. /tmp/spreads.db copied "
        "from the container at /app/trading/data.db)",
    )
    parser.add_argument("--output", type=str, default="docs/backtests")

    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"ERROR: database not found at {args.db}", file=sys.stderr)
        return 1

    print(f"Loading {args.days} days of spread history from {args.db}...")
    observations = await load_spread_history(args.db, args.days)
    print(f"Loaded {len(observations)} observations")

    result = run_backtest(
        observations, args.days, args.min_profit_bps, args.position_size
    )

    print(f"\nBacktest Results (requested {args.days} days, "
          f"actual coverage {result.coverage_days:.2f} days)")
    print(f"Observations: {result.observations_count}")
    print(f"Total Trades: {result.total_trades}")
    if result.total_trades > 0:
        print(f"Win Rate: {result.winning_trades / result.total_trades * 100:.1f}%")
        print(f"Total P&L: ${result.total_pnl_usd:.2f}")
        print(f"Avg Profit: {result.avg_profit_bps:.2f} bps")
        print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.3f}")
    print(f"\nRecommendation: {result.recommendation}")
    print(f"Reason: {result.recommendation_reason}\n")

    output_dir = Path(args.output)
    md_path, csv_path = generate_report(
        result, output_dir, args.db, args.min_profit_bps, args.position_size
    )
    print(f"Report written to: {md_path}")
    print(f"Trades CSV: {csv_path}")

    # Exit 1 on insufficient data so CI / agent tooling sees a failure signal.
    if result.recommendation == "INSUFFICIENT_DATA":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
