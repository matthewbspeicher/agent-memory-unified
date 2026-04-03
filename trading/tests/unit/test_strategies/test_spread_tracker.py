# python/tests/unit/test_strategies/test_spread_tracker.py
from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from data.events import EventBus
from strategies.spread_tracker import SpreadTracker


def _make_tracker(match_index=None, alert_threshold=8):
    store = AsyncMock()
    store.record = AsyncMock()
    bus = EventBus()
    kalshi_ds = AsyncMock()
    kalshi_ds.get_market = AsyncMock(return_value=MagicMock(
        ticker="K1", yes_bid=45, yes_ask=55, yes_last=50,
        volume_24h=1000, category="politics",
        close_time=None, title="Test market",
    ))
    tracker = SpreadTracker(
        spread_store=store,
        match_index=match_index or {"tok1": "K1"},
        event_bus=bus,
        kalshi_ds=kalshi_ds,
        alert_threshold_cents=alert_threshold,
    )
    return tracker, store, bus, kalshi_ds


class TestSpreadTracker:
    async def test_records_observation_on_quote_event(self):
        tracker, store, bus, _ = _make_tracker()
        # Publish an event and let tracker process it
        task = asyncio.create_task(tracker.run())
        await asyncio.sleep(0)  # yield to let tracker subscribe
        await bus.publish("polymarket.quote", {
            "condition_id": "tok1",
            "yes_cents": 60,
            "timestamp": 0.0,
        })
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        store.record.assert_called_once()

    async def test_ignores_unmatched_token(self):
        tracker, store, bus, _ = _make_tracker(match_index={"tokOther": "K1"})
        task = asyncio.create_task(tracker.run())
        await asyncio.sleep(0)
        await bus.publish("polymarket.quote", {
            "condition_id": "tok_unknown",
            "yes_cents": 60,
            "timestamp": 0.0,
        })
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        store.record.assert_not_called()

    async def test_publishes_arb_spread_event_above_threshold(self):
        tracker, store, bus, _ = _make_tracker(alert_threshold=8)
        received = []

        async def capture():
            async for evt in bus.subscribe():
                if evt["topic"] == "arb.spread":
                    received.append(evt)
                    break

        capture_task = asyncio.create_task(capture())
        run_task = asyncio.create_task(tracker.run())
        await asyncio.sleep(0)
        # yes_ask=55 on Kalshi (buy cost), yes_cents=70 on Polymarket → gap=15 > threshold=8
        await bus.publish("polymarket.quote", {
            "condition_id": "tok1",
            "yes_cents": 70,
            "timestamp": 0.0,
        })
        await asyncio.sleep(0.1)
        run_task.cancel()
        capture_task.cancel()
        try:
            await run_task
        except asyncio.CancelledError:
            pass
        try:
            await capture_task
        except asyncio.CancelledError:
            pass
        assert len(received) >= 1

    async def test_no_arb_event_below_threshold(self):
        tracker, store, bus, _ = _make_tracker(alert_threshold=20)
        received = []

        async def capture():
            async for evt in bus.subscribe():
                if evt["topic"] == "arb.spread":
                    received.append(evt)

        capture_task = asyncio.create_task(capture())
        run_task = asyncio.create_task(tracker.run())
        await asyncio.sleep(0)
        # gap = |55 - 52| = 3 (using ask=55), below threshold 20
        await bus.publish("polymarket.quote", {
            "condition_id": "tok1",
            "yes_cents": 52,
            "timestamp": 0.0,
        })
        await asyncio.sleep(0.1)
        run_task.cancel()
        capture_task.cancel()
        for t in [run_task, capture_task]:
            try:
                await t
            except asyncio.CancelledError:
                pass
        assert len(received) == 0

    async def test_spread_tracker_uses_ask_for_kalshi_price(self):
        """SpreadTracker should use yes_ask (cost-to-buy) not yes_bid for Kalshi leg."""
        import aiosqlite
        from storage.db import init_db
        from storage.spreads import SpreadStore

        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await init_db(db)
        store = SpreadStore(db)
        bus = EventBus()

        kalshi_ds = AsyncMock()
        kalshi_ds.get_market = AsyncMock(return_value=MagicMock(
            ticker="KTEST", yes_bid=38, yes_ask=42, volume_24h=500,
        ))

        tracker = SpreadTracker(
            spread_store=store,
            match_index={"PTEST": "KTEST"},
            event_bus=bus,
            kalshi_ds=kalshi_ds,
            alert_threshold_cents=5,
        )

        await tracker._handle_quote({"condition_id": "PTEST", "yes_cents": 60})

        history = await store.get_history("KTEST", "PTEST", hours=1)
        assert len(history) == 1
        assert history[0].kalshi_cents == 42, f"Expected 42 (ask), got {history[0].kalshi_cents}"
        await db.close()
