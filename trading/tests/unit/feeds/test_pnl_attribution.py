"""Unit tests for FeedArbPnLAttribution.

Covers the v1 attribution contract:
- Expired-signal marking runs even with no brokers
- Honest-tracker rule: no rollup row when there are no real fills
- Kalshi fills joined via client_order_id → signal marked filled
- Polymarket fills joined via signal_order_map → signal marked filled
- Realized PnL from edge_cents × filled notional × 0.5 (half-credit per leg)
- Scaled PnL = realized × (scaled / real)
- Cumulative PnL carries across rollups
- Broker fetch failure is swallowed (tick continues)
- Unknown signal_id does not crash realized-PnL lookup
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from feeds.pnl_attribution import (
    FeedArbPnLAttribution,
    RealizedFill,
)
from storage.db import init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


async def _seed_signal(
    db,
    signal_id: str,
    *,
    ts: datetime,
    expires_at: datetime,
    edge_cents: float = 10.0,
    max_size_usd: float = 100.0,
    outcome: str | None = None,
):
    await db.execute(
        "INSERT INTO feed_arb_signals "
        "(signal_id, ts, pair_kalshi_ticker, pair_kalshi_side, "
        " pair_poly_token_id, pair_poly_side, edge_cents, "
        " max_size_at_edge_usd, expires_at, outcome, raw_signal) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            signal_id,
            ts.isoformat(),
            "KXTEST",
            "SELL",
            "0x" + "a" * 64,
            "BUY",
            edge_cents,
            max_size_usd,
            expires_at.isoformat(),
            outcome,
            '{"signal_id":"%s"}' % signal_id,
        ),
    )
    await db.commit()


async def _seed_order_map(db, order_hash: str, signal_id: str, venue: str):
    await db.execute(
        "INSERT INTO signal_order_map (order_hash, signal_id, venue) VALUES (?, ?, ?)",
        (order_hash, signal_id, venue),
    )
    await db.commit()


async def _outcome(db, signal_id: str) -> str | None:
    cursor = await db.execute(
        "SELECT outcome FROM feed_arb_signals WHERE signal_id = ?", (signal_id,)
    )
    row = await cursor.fetchone()
    return row["outcome"] if row else None


async def _rollup_count(db) -> int:
    cursor = await db.execute("SELECT COUNT(*) AS n FROM feed_arb_pnl_rollup")
    row = await cursor.fetchone()
    return int(row["n"])


# ---------------------------------------------------------------------------
# Honest-tracker rule: no rollup row when no fills
# ---------------------------------------------------------------------------


class TestHonestTrackerNoFills:
    async def test_no_brokers_no_rollup(self, db):
        """When no brokers are wired, no rollup should ever be written,
        even if signals exist."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_signal(
            db, "01ACTIVE0000000000000000AA", ts=now, expires_at=now + timedelta(minutes=5)
        )

        job = FeedArbPnLAttribution(db=db, clock=lambda: now)
        result = await job.tick()

        assert result is None
        assert await _rollup_count(db) == 0

    async def test_brokers_but_no_fills_no_rollup(self, db):
        """Brokers wired but returning empty → still no rollup."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        kalshi = MagicMock()
        kalshi._client.get_order_history = AsyncMock(return_value=[])
        polymarket = MagicMock()
        polymarket.client.get_orders = MagicMock(return_value=[])

        job = FeedArbPnLAttribution(
            db=db,
            kalshi_broker=kalshi,
            polymarket_broker=polymarket,
            clock=lambda: now,
        )
        result = await job.tick()

        assert result is None
        assert await _rollup_count(db) == 0


# ---------------------------------------------------------------------------
# Expired-signal marking — runs unconditionally
# ---------------------------------------------------------------------------


class TestMarkExpired:
    async def test_expired_signal_marked_missed(self, db):
        """A signal past its expires_at with outcome=NULL gets marked 'missed'."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        expired_ts = now - timedelta(hours=1)
        await _seed_signal(
            db, "01EXPIRED00000000000000AA", ts=expired_ts, expires_at=expired_ts + timedelta(minutes=5)
        )

        job = FeedArbPnLAttribution(db=db, clock=lambda: now)
        await job.tick()

        assert await _outcome(db, "01EXPIRED00000000000000AA") == "missed"

    async def test_active_signal_not_marked(self, db):
        """A signal still within expires_at stays NULL."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_signal(
            db, "01ACTIVE0000000000000000AA", ts=now, expires_at=now + timedelta(minutes=5)
        )

        job = FeedArbPnLAttribution(db=db, clock=lambda: now)
        await job.tick()

        assert await _outcome(db, "01ACTIVE0000000000000000AA") is None

    async def test_already_filled_signal_not_remarked(self, db):
        """A filled signal that later expires stays 'filled', not 'missed'."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        expired_ts = now - timedelta(hours=1)
        await _seed_signal(
            db,
            "01FILLED00000000000000AAAA",
            ts=expired_ts,
            expires_at=expired_ts + timedelta(minutes=5),
            outcome="filled",
        )

        job = FeedArbPnLAttribution(db=db, clock=lambda: now)
        await job.tick()

        assert await _outcome(db, "01FILLED00000000000000AAAA") == "filled"


# ---------------------------------------------------------------------------
# Kalshi fills — joined via client_order_id
# ---------------------------------------------------------------------------


def _kalshi_order(
    *,
    client_order_id: str,
    ticker: str = "KXTEST",
    contracts_filled: int = 50,
    avg_cents: int = 40,
    fees_cents: int = 5,
    status: str = "executed",
    updated: str = "2026-04-16T12:00:00+00:00",
):
    return {
        "order_id": "k-order-1",
        "client_order_id": client_order_id,
        "status": status,
        "ticker": ticker,
        "contracts_filled": contracts_filled,
        "avg_price": avg_cents,
        "fees": fees_cents,
        "updated_time": updated,
    }


class TestKalshiFills:
    async def test_kalshi_fill_marks_signal_filled(self, db):
        now = datetime(2026, 4, 16, 12, 1, 0, tzinfo=timezone.utc)
        sig_ts = now - timedelta(minutes=1)
        await _seed_signal(
            db, "01KSIG000000000000000000AA", ts=sig_ts, expires_at=sig_ts + timedelta(minutes=5)
        )

        kalshi = MagicMock()
        kalshi._client.get_order_history = AsyncMock(
            return_value=[
                _kalshi_order(
                    client_order_id="01KSIG000000000000000000AA",
                    updated=sig_ts.isoformat(),
                )
            ]
        )

        job = FeedArbPnLAttribution(
            db=db, kalshi_broker=kalshi, clock=lambda: now
        )
        result = await job.tick()

        assert result is not None
        assert "01KSIG000000000000000000AA" in result.filled_signal_ids
        assert await _outcome(db, "01KSIG000000000000000000AA") == "filled"
        assert await _rollup_count(db) == 1

    async def test_kalshi_unmatched_client_order_id_skipped(self, db):
        """A Kalshi fill with a client_order_id we don't know about
        should not be attributed to any signal. Importantly: tick should
        still complete cleanly."""
        now = datetime(2026, 4, 16, 12, 1, 0, tzinfo=timezone.utc)
        kalshi = MagicMock()
        kalshi._client.get_order_history = AsyncMock(
            return_value=[
                _kalshi_order(
                    client_order_id="01UNKNOWN0000000000000000",
                    updated=now.isoformat(),
                )
            ]
        )

        job = FeedArbPnLAttribution(
            db=db, kalshi_broker=kalshi, clock=lambda: now
        )
        result = await job.tick()

        # Fill present but its signal doesn't exist in the DB. Rollup
        # IS written because fills are counted pre-lookup, but realized
        # resolves to $0 since _realized_from_fill can't find the signal.
        assert result is not None
        assert result.realized_pnl_usd == Decimal("0")

    async def test_kalshi_pending_order_ignored(self, db):
        """Non-terminal statuses (pending/resting) don't produce fills."""
        now = datetime(2026, 4, 16, 12, 1, 0, tzinfo=timezone.utc)
        await _seed_signal(
            db, "01KSIGR00000000000000000AA", ts=now, expires_at=now + timedelta(minutes=5)
        )
        kalshi = MagicMock()
        kalshi._client.get_order_history = AsyncMock(
            return_value=[
                _kalshi_order(
                    client_order_id="01KSIGR00000000000000000AA",
                    status="resting",
                    updated=now.isoformat(),
                )
            ]
        )

        job = FeedArbPnLAttribution(
            db=db, kalshi_broker=kalshi, clock=lambda: now
        )
        result = await job.tick()

        assert result is None
        assert await _outcome(db, "01KSIGR00000000000000000AA") is None

    async def test_kalshi_fetch_failure_swallowed(self, db):
        """Kalshi API error should not crash the tick; it should return
        no fills and proceed to mark expired signals."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        kalshi = MagicMock()
        kalshi._client.get_order_history = AsyncMock(
            side_effect=RuntimeError("kalshi 500")
        )

        job = FeedArbPnLAttribution(
            db=db, kalshi_broker=kalshi, clock=lambda: now
        )
        # Must not raise
        await job.tick()


# ---------------------------------------------------------------------------
# Polymarket fills — joined via signal_order_map
# ---------------------------------------------------------------------------


def _poly_order(
    *,
    order_hash: str,
    size_matched: float = 50.0,
    price: float = 0.40,
    status: str = "FILLED",
    updated: str = "2026-04-16T12:00:00+00:00",
):
    return {
        "id": order_hash,
        "status": status,
        "size_matched": size_matched,
        "price": price,
        "updated_at": updated,
        "market": "0x" + "a" * 64,
    }


class TestPolymarketFills:
    async def test_polymarket_fill_via_order_map(self, db):
        now = datetime(2026, 4, 16, 12, 1, 0, tzinfo=timezone.utc)
        sig_ts = now - timedelta(minutes=1)
        await _seed_signal(
            db,
            "01PSIG000000000000000000AA",
            ts=sig_ts,
            expires_at=sig_ts + timedelta(minutes=5),
        )
        await _seed_order_map(
            db, "0xorderhash-1", "01PSIG000000000000000000AA", "polymarket"
        )

        polymarket = MagicMock()
        polymarket.client.get_orders = MagicMock(
            return_value=[
                _poly_order(order_hash="0xorderhash-1", updated=sig_ts.isoformat())
            ]
        )

        job = FeedArbPnLAttribution(
            db=db, polymarket_broker=polymarket, clock=lambda: now
        )
        result = await job.tick()

        assert result is not None
        assert "01PSIG000000000000000000AA" in result.filled_signal_ids
        assert await _outcome(db, "01PSIG000000000000000000AA") == "filled"

    async def test_polymarket_unmapped_order_hash_skipped(self, db):
        """A Polymarket fill whose order_hash isn't in signal_order_map
        is quietly skipped (not attributed, not rolled up)."""
        now = datetime(2026, 4, 16, 12, 1, 0, tzinfo=timezone.utc)
        polymarket = MagicMock()
        polymarket.client.get_orders = MagicMock(
            return_value=[
                _poly_order(order_hash="0xunknown", updated=now.isoformat())
            ]
        )

        job = FeedArbPnLAttribution(
            db=db, polymarket_broker=polymarket, clock=lambda: now
        )
        result = await job.tick()

        assert result is None


# ---------------------------------------------------------------------------
# Realized PnL math — edge_cents × filled × 0.5 per leg
# ---------------------------------------------------------------------------


class TestRealizedPnL:
    async def test_realized_math_pro_rates_by_fill(self, db):
        """A fill that covers 50% of max_size_usd at 10¢ edge should
        produce edge × filled × 0.5 (half-credit per leg) realized."""
        now = datetime(2026, 4, 16, 12, 1, 0, tzinfo=timezone.utc)
        sig_ts = now - timedelta(minutes=1)
        await _seed_signal(
            db,
            "01EDGE0000000000000000000A",
            ts=sig_ts,
            expires_at=sig_ts + timedelta(minutes=5),
            edge_cents=10.0,
            max_size_usd=100.0,
        )
        # 50 contracts @ $1.00 each = $50 filled (50% of $100 max size)
        kalshi = MagicMock()
        kalshi._client.get_order_history = AsyncMock(
            return_value=[
                _kalshi_order(
                    client_order_id="01EDGE0000000000000000000A",
                    contracts_filled=50,
                    avg_cents=100,  # $1.00
                    fees_cents=0,
                    updated=sig_ts.isoformat(),
                )
            ]
        )

        job = FeedArbPnLAttribution(
            db=db, kalshi_broker=kalshi, clock=lambda: now
        )
        result = await job.tick()

        # realized = $50 filled × 0.10 edge × 1.0 (50%/max_size capped) × 0.5
        # Wait — filled_usd=50, max_size=100, so fill_fraction=0.5.
        # realized = 50 × 0.10 × 0.5 × 0.5 = 1.25 (half-credit leg × fill_fraction clip)
        # Actually the formula is:
        #   filled_usd × per_dollar_edge × min(fill_fraction, 1) / 2
        #   = 50 × 0.10 × 0.5 / 2 = 1.25
        assert result.realized_pnl_usd == Decimal("1.25")

    async def test_realized_zero_when_signal_unknown(self, db):
        """Fill for a signal_id that isn't in feed_arb_signals → $0 realized."""
        now = datetime(2026, 4, 16, 12, 1, 0, tzinfo=timezone.utc)
        kalshi = MagicMock()
        kalshi._client.get_order_history = AsyncMock(
            return_value=[
                _kalshi_order(
                    client_order_id="01NOSIGID000000000000000A",
                    updated=now.isoformat(),
                )
            ]
        )

        job = FeedArbPnLAttribution(
            db=db, kalshi_broker=kalshi, clock=lambda: now
        )
        result = await job.tick()

        assert result.realized_pnl_usd == Decimal("0")

    async def test_fees_subtract_from_realized(self, db):
        now = datetime(2026, 4, 16, 12, 1, 0, tzinfo=timezone.utc)
        sig_ts = now - timedelta(minutes=1)
        await _seed_signal(
            db,
            "01FEE00000000000000000000A",
            ts=sig_ts,
            expires_at=sig_ts + timedelta(minutes=5),
            edge_cents=10.0,
            max_size_usd=100.0,
        )
        # Same $50 fill as above but with 25¢ in fees. Expected:
        # 1.25 - 0.25 = 1.00
        kalshi = MagicMock()
        kalshi._client.get_order_history = AsyncMock(
            return_value=[
                _kalshi_order(
                    client_order_id="01FEE00000000000000000000A",
                    contracts_filled=50,
                    avg_cents=100,
                    fees_cents=25,
                    updated=sig_ts.isoformat(),
                )
            ]
        )

        job = FeedArbPnLAttribution(
            db=db, kalshi_broker=kalshi, clock=lambda: now
        )
        result = await job.tick()

        assert result.realized_pnl_usd == Decimal("1.00")


# ---------------------------------------------------------------------------
# Scaled PnL + cumulative
# ---------------------------------------------------------------------------


class TestScaledAndCumulative:
    async def test_scaled_pnl_applies_factor(self, db):
        """Rollup row stores realized × (scaled / real) in scaled_*_usd cols."""
        now = datetime(2026, 4, 16, 12, 1, 0, tzinfo=timezone.utc)
        sig_ts = now - timedelta(minutes=1)
        await _seed_signal(
            db,
            "01SCALE00000000000000000AA",
            ts=sig_ts,
            expires_at=sig_ts + timedelta(minutes=5),
            edge_cents=10.0,
            max_size_usd=100.0,
        )
        kalshi = MagicMock()
        kalshi._client.get_order_history = AsyncMock(
            return_value=[
                _kalshi_order(
                    client_order_id="01SCALE00000000000000000AA",
                    contracts_filled=50,
                    avg_cents=100,
                    fees_cents=0,
                    updated=sig_ts.isoformat(),
                )
            ]
        )

        # Scaled from $11k → $250k (factor ≈ 22.727)
        job = FeedArbPnLAttribution(
            db=db,
            kalshi_broker=kalshi,
            clock=lambda: now,
            real_notional_usd=11000,
            scaled_notional_usd=250000,
        )
        await job.tick()

        cursor = await db.execute(
            "SELECT realized_pnl_usd, scaled_realized_pnl_usd, scaling_assumption "
            "FROM feed_arb_pnl_rollup ORDER BY rollup_ts DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        real = Decimal(str(row["realized_pnl_usd"]))
        scaled = Decimal(str(row["scaled_realized_pnl_usd"]))
        # 1.25 × (250000/11000) ≈ 28.41
        assert real == Decimal("1.25")
        assert abs(scaled - Decimal("1.25") * Decimal("250000") / Decimal("11000")) < Decimal("0.01")
        assert "Linearly scaled" in row["scaling_assumption"]

    async def test_cumulative_sums_across_rollups(self, db):
        """Second rollup's cumulative column includes the first rollup's
        realized."""
        t0 = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(seconds=60)

        async def run_tick_with_fill(signal_id: str, at: datetime):
            await _seed_signal(
                db,
                signal_id,
                ts=at - timedelta(minutes=1),
                expires_at=at + timedelta(minutes=5),
                edge_cents=10.0,
                max_size_usd=100.0,
            )
            kalshi = MagicMock()
            kalshi._client.get_order_history = AsyncMock(
                return_value=[
                    _kalshi_order(
                        client_order_id=signal_id,
                        contracts_filled=50,
                        avg_cents=100,
                        fees_cents=0,
                        updated=at.isoformat(),
                    )
                ]
            )
            job = FeedArbPnLAttribution(
                db=db, kalshi_broker=kalshi, clock=lambda: at
            )
            await job.tick()

        await run_tick_with_fill("01CUM100000000000000000AA", t0)
        await run_tick_with_fill("01CUM200000000000000000AA", t1)

        cursor = await db.execute(
            "SELECT rollup_ts, realized_pnl_usd, cumulative_pnl_usd "
            "FROM feed_arb_pnl_rollup ORDER BY rollup_ts ASC"
        )
        rows = await cursor.fetchall()
        assert len(rows) == 2
        r0, r1 = rows
        # Each tick realizes 1.25; cumulative at t0 = 1.25, at t1 = 2.50
        assert Decimal(str(r0["cumulative_pnl_usd"])) == Decimal("1.25")
        assert Decimal(str(r1["cumulative_pnl_usd"])) == Decimal("2.50")
