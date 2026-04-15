"""Replay engine for prediction-market strategies against historical snapshots.

Simplifications (v0.1):
- One open contract per ticker (no pyramiding)
- Fills at the snapshot's yes_price_cents (no slippage model yet)
- YES resolves at 100¢, NO at 0¢
- Fees applied per contract on entry only
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from backtest.metrics import BacktestMetrics, compute_metrics


@dataclass(frozen=True)
class HistoricalSnapshot:
    ticker: str
    ts: int
    yes_price_cents: int
    resolved: bool = False
    resolution: str | None = None  # "YES" | "NO"


@dataclass
class BacktestResult:
    metrics: BacktestMetrics
    trades: list[dict] = field(default_factory=list)


class _StrategyLike(Protocol):
    name: str

    async def on_snapshot(self, snap: HistoricalSnapshot) -> list[dict]: ...


class PredictionMarketBacktest:
    def __init__(
        self,
        strategy: _StrategyLike,
        snapshots: list[HistoricalSnapshot],
        starting_capital_cents: int,
        fee_cents_per_contract: int = 1,
    ) -> None:
        self._strategy = strategy
        self._snapshots = snapshots
        self._starting = starting_capital_cents
        self._fee = fee_cents_per_contract

    async def run(self) -> BacktestResult:
        open_positions: dict[str, dict] = {}
        closed_trades: list[dict] = []

        for snap in self._snapshots:
            if snap.resolved:
                pos = open_positions.pop(snap.ticker, None)
                if pos is not None:
                    settle = 100 if snap.resolution == "YES" else 0
                    gross = (settle - pos["entry_cents"]) * pos["size"]
                    closed_trades.append({
                        "ticker": snap.ticker,
                        "entry_ts": pos["entry_ts"],
                        "exit_ts": snap.ts,
                        "pnl_cents": gross - pos["fees"],
                    })
                continue

            if snap.ticker in open_positions:
                continue

            orders = await self._strategy.on_snapshot(snap)
            for order in orders:
                if order.get("ticker") != snap.ticker:
                    continue
                size = int(order["size"])
                open_positions[snap.ticker] = {
                    "entry_ts": snap.ts,
                    "entry_cents": int(order["price_cents"]),
                    "size": size,
                    "fees": self._fee * size,
                }

        return BacktestResult(
            metrics=compute_metrics(closed_trades, self._starting),
            trades=closed_trades,
        )
