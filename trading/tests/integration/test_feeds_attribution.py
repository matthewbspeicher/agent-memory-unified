"""Integration: publisher → feed_arb_signals → attribution → rollup.

Exercises the real event loop + real publisher + real attribution job
against an in-memory SQLite DB. Complements the unit tests by proving
the two jobs compose correctly — no mock-only paths.

Scenario 1: Publisher writes a signal; time passes past expires_at;
attribution marks it 'missed'; dashboard sees the outcome.

Scenario 2: Publisher writes a signal; a mock Kalshi broker reports a
fill with matching client_order_id; attribution marks it 'filled' and
writes a rollup row with realized + scaled PnL and the assumption text.

Per feedback_integration_tests_mocked: no pure-mock tests. The broker
itself is mocked (we can't run against Kalshi live in CI), but every
other component is the real class.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from data.events import EventBus
from feeds.pnl_attribution import FeedArbPnLAttribution
from feeds.publisher import FeedPublisher
from storage.db import init_db


pytestmark = pytest.mark.integration


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


def _arb_spread_event(signal_id: str, gap_cents: float = 50.0):
    """Build an arb.spread event payload matching what
    strategies/cross_platform_arb.py emits."""
    return {
        "signal_id": signal_id,
        "observation_id": 1,
        "kalshi_ticker": "KXINTEG-TEST",
        "poly_ticker": "0x" + "a" * 64,
        "kalshi_cents": 70,
        "poly_cents": 70 - int(gap_cents),
        "gap_cents": gap_cents,
        "match_score": 0.85,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


async def _drive_publisher(bus: EventBus, pub: FeedPublisher, events: list[dict]):
    """Run the publisher against a scripted event sequence, bounded."""
    task = asyncio.create_task(pub.run())
    try:
        await asyncio.sleep(0.01)  # let subscription register
        for data in events:
            await bus.publish("arb.spread", data)
        # Wait for rows to materialize.
        for _ in range(50):
            cursor = await pub._db.execute(
                "SELECT COUNT(*) AS n FROM feed_arb_signals"
            )
            row = await cursor.fetchone()
            if int(row["n"]) >= len(events):
                return
            await asyncio.sleep(0.02)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestAttributionPipelineNoFills:
    async def test_publisher_emits_then_attribution_marks_missed(self, db):
        """Publisher writes a signal; its expires_at passes; attribution
        marks it 'missed'. No rollup row written (honest-tracker rule)."""
        bus = EventBus()
        pub = FeedPublisher(
            db=db,
            event_bus=bus,
            default_expiration_seconds=1,  # force quick expiry
        )
        await _drive_publisher(
            bus, pub, [_arb_spread_event("01INTEGEXP000000000000000")]
        )

        # Confirm signal landed, outcome=NULL initially
        cursor = await db.execute(
            "SELECT signal_id, outcome, expires_at FROM feed_arb_signals"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["outcome"] is None

        # Advance clock past expires_at; attribution ticks.
        later = datetime.now(timezone.utc) + timedelta(minutes=5)
        job = FeedArbPnLAttribution(db=db, clock=lambda: later)
        result = await job.tick()

        # No fills → no rollup
        assert result is None
        cursor = await db.execute("SELECT COUNT(*) AS n FROM feed_arb_pnl_rollup")
        assert (await cursor.fetchone())["n"] == 0

        # But outcome is now 'missed'
        cursor = await db.execute(
            "SELECT outcome FROM feed_arb_signals WHERE signal_id = ?",
            ("01INTEGEXP000000000000000",),
        )
        assert (await cursor.fetchone())["outcome"] == "missed"


class TestAttributionPipelineWithKalshiFill:
    async def test_publisher_emits_then_kalshi_fill_marks_filled_writes_rollup(
        self, db
    ):
        """End-to-end: publisher writes signal, Kalshi reports a fill
        with matching client_order_id, attribution marks filled +
        writes rollup row with spec-shape columns populated."""
        bus = EventBus()
        pub = FeedPublisher(db=db, event_bus=bus)
        await _drive_publisher(
            bus, pub, [_arb_spread_event("01INTEGFILL0000000000000A", gap_cents=50.0)]
        )

        # Signal is live in the DB. Now mock a Kalshi fill.
        now = datetime.now(timezone.utc) + timedelta(seconds=30)
        kalshi = MagicMock()
        kalshi._client.get_order_history = AsyncMock(
            return_value=[
                {
                    "order_id": "k-1",
                    "client_order_id": "01INTEGFILL0000000000000A",
                    "status": "executed",
                    "ticker": "KXINTEG-TEST",
                    "contracts_filled": 50,
                    "avg_price": 100,  # $1.00 — matches filled_usd=50 = 50% of $100 max
                    "fees": 0,
                    "updated_time": now.isoformat(),
                }
            ]
        )

        job = FeedArbPnLAttribution(
            db=db,
            kalshi_broker=kalshi,
            clock=lambda: now,
            real_notional_usd=11000,
            scaled_notional_usd=250000,
        )
        result = await job.tick()

        # Signal marked filled
        cursor = await db.execute(
            "SELECT outcome FROM feed_arb_signals WHERE signal_id = ?",
            ("01INTEGFILL0000000000000A",),
        )
        assert (await cursor.fetchone())["outcome"] == "filled"

        # Rollup row written with expected shape
        cursor = await db.execute(
            "SELECT realized_pnl_usd, cumulative_pnl_usd, "
            "       scaled_realized_pnl_usd, scaling_assumption, "
            "       closed_position_count "
            "FROM feed_arb_pnl_rollup ORDER BY rollup_ts DESC LIMIT 1"
        )
        rollup = await cursor.fetchone()
        assert rollup is not None

        # 50¢ edge × $50 filled × 0.5 (fill fraction) / 2 (per leg) = $0.625
        # Wait — recheck: edge was gross 50 cents, so per_dollar_edge = 0.50
        # realized = filled_usd × per_dollar_edge × fill_fraction_capped / 2
        #         = 50 × 0.50 × 0.5 / 2 = 6.25
        assert Decimal(str(rollup["realized_pnl_usd"])) == Decimal("6.25")
        assert Decimal(str(rollup["cumulative_pnl_usd"])) == Decimal("6.25")
        # Scaled × (250000/11000) ≈ 22.727
        scaled = Decimal(str(rollup["scaled_realized_pnl_usd"]))
        assert abs(scaled - Decimal("6.25") * Decimal("250000") / Decimal("11000")) < Decimal("0.01")
        assert "Linearly scaled" in rollup["scaling_assumption"]
        assert rollup["closed_position_count"] == 1
