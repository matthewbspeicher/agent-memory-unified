"""Replay engine for prediction-market strategies."""
from __future__ import annotations

import pytest

from backtest.prediction_market import HistoricalSnapshot, PredictionMarketBacktest


class _BelowSixtyBuyer:
    """Emits a BUY for 10 contracts at 55¢ whenever price < 60¢."""
    name = "stub"

    async def on_snapshot(self, snap: HistoricalSnapshot):
        if snap.yes_price_cents < 60:
            return [{"ticker": snap.ticker, "side": "BUY", "price_cents": 55, "size": 10}]
        return []


@pytest.mark.asyncio
async def test_replay_executes_strategy_orders_and_settles_at_resolution():
    snapshots = [
        HistoricalSnapshot(ticker="T1", ts=1, yes_price_cents=55),
        HistoricalSnapshot(ticker="T1", ts=2, yes_price_cents=65),
        HistoricalSnapshot(ticker="T1", ts=3, yes_price_cents=100, resolved=True, resolution="YES"),
    ]
    engine = PredictionMarketBacktest(
        strategy=_BelowSixtyBuyer(),
        snapshots=snapshots,
        starting_capital_cents=1000,
        fee_cents_per_contract=1,
    )
    result = await engine.run()

    # Bought 10 contracts @ 55¢, paid 10 × 1¢ fee, YES resolves @ 100¢.
    # PnL = (100 - 55) × 10 − 10 = 440.
    assert result.metrics.num_trades == 1
    assert result.metrics.total_pnl_cents == 440
    assert result.trades[0]["ticker"] == "T1"
    assert result.trades[0]["entry_ts"] == 1
    assert result.trades[0]["exit_ts"] == 3


@pytest.mark.asyncio
async def test_replay_no_order_means_no_trades():
    class _Idle:
        name = "idle"
        async def on_snapshot(self, snap):
            return []

    snapshots = [
        HistoricalSnapshot(ticker="T2", ts=1, yes_price_cents=55),
        HistoricalSnapshot(ticker="T2", ts=2, yes_price_cents=100, resolved=True, resolution="NO"),
    ]
    result = await PredictionMarketBacktest(
        strategy=_Idle(),
        snapshots=snapshots,
        starting_capital_cents=1000,
    ).run()
    assert result.metrics.num_trades == 0
    assert result.metrics.total_pnl_cents == 0


@pytest.mark.asyncio
async def test_replay_no_pyramiding():
    # Strategy tries to BUY on every snapshot, but engine must not re-enter
    # while a position is still open.
    class _AlwaysBuy:
        name = "always"
        async def on_snapshot(self, snap):
            return [{"ticker": snap.ticker, "side": "BUY", "price_cents": 50, "size": 10}]

    snapshots = [
        HistoricalSnapshot(ticker="T3", ts=1, yes_price_cents=50),
        HistoricalSnapshot(ticker="T3", ts=2, yes_price_cents=55),
        HistoricalSnapshot(ticker="T3", ts=3, yes_price_cents=60),
        HistoricalSnapshot(ticker="T3", ts=4, yes_price_cents=0, resolved=True, resolution="NO"),
    ]
    result = await PredictionMarketBacktest(
        strategy=_AlwaysBuy(),
        snapshots=snapshots,
        starting_capital_cents=1000,
        fee_cents_per_contract=0,
    ).run()
    # One trade opened at ts=1, closed at NO resolution (0¢). PnL = -50 × 10 = -500
    assert result.metrics.num_trades == 1
    assert result.metrics.total_pnl_cents == -500


@pytest.mark.asyncio
async def test_replay_no_resolution_leaves_position_open():
    # A position that never resolves is not counted as a closed trade.
    snapshots = [
        HistoricalSnapshot(ticker="T4", ts=1, yes_price_cents=50),
        HistoricalSnapshot(ticker="T4", ts=2, yes_price_cents=55),
    ]
    result = await PredictionMarketBacktest(
        strategy=_BelowSixtyBuyer(),
        snapshots=snapshots,
        starting_capital_cents=1000,
    ).run()
    assert result.metrics.num_trades == 0
