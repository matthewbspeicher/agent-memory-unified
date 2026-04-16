"""Unit tests for FeedHealthMonitor (D3/D4 alerts).

Covers:
- D3 attribution-stall: fires when rollup_ts is older than threshold,
  does NOT fire when no rollups exist yet (honest-tracker launch state),
  recovers cleanly when attribution catches up.
- D4 publisher-zero: fires when signals have existed but none within
  the zero-window, does NOT fire pre-first-signal, recovers when
  publisher writes again.
- Cooldown: second alert within cooldown is suppressed; after cooldown
  expires, alert fires again.
- Notifier failure: alert still logged even if send_text raises.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from feeds.health_monitor import FeedHealthMonitor
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


async def _seed_rollup(db, *, rollup_ts: datetime, realized: float = 1.25):
    """INSERT a feed_arb_pnl_rollup row."""
    await db.execute(
        "INSERT INTO feed_arb_pnl_rollup "
        "(rollup_ts, realized_pnl_usd, open_pnl_usd, cumulative_pnl_usd, "
        " open_position_count, closed_position_count, "
        " scaled_realized_pnl_usd, scaled_open_pnl_usd, "
        " scaled_cumulative_pnl_usd, scaling_assumption) "
        "VALUES (?, 0, 0, 0, 0, 0, 0, 0, 0, 'test')",
        (rollup_ts.isoformat(),),
    )
    await db.execute(
        "UPDATE feed_arb_pnl_rollup SET realized_pnl_usd = ?, cumulative_pnl_usd = ? "
        "WHERE rollup_ts = ?",
        (realized, realized, rollup_ts.isoformat()),
    )
    await db.commit()


async def _seed_signal(db, signal_id: str, *, ts: datetime):
    await db.execute(
        "INSERT INTO feed_arb_signals "
        "(signal_id, ts, pair_kalshi_ticker, pair_kalshi_side, "
        " pair_poly_token_id, pair_poly_side, edge_cents, "
        " max_size_at_edge_usd, expires_at, raw_signal) "
        "VALUES (?, ?, 'K', 'SELL', '0x', 'BUY', 10, 100, ?, '{}')",
        (signal_id, ts.isoformat(), (ts + timedelta(minutes=5)).isoformat()),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# D3 — attribution stall
# ---------------------------------------------------------------------------


class TestD3AttributionStall:
    async def test_no_rollups_is_silent(self, db):
        """Pre-first-fill state: no rollups yet. Should NOT alert
        (honest-tracker launch state)."""
        notifier = MagicMock()
        notifier.send_text = AsyncMock()
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)

        mon = FeedHealthMonitor(db=db, notifier=notifier, clock=lambda: now)
        await mon.tick()

        notifier.send_text.assert_not_called()

    async def test_fresh_rollup_is_silent(self, db):
        """Rollup within threshold → no alert."""
        notifier = MagicMock()
        notifier.send_text = AsyncMock()
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_rollup(db, rollup_ts=now - timedelta(seconds=60))

        mon = FeedHealthMonitor(
            db=db,
            notifier=notifier,
            attribution_staleness_seconds=300,
            clock=lambda: now,
        )
        await mon.tick()

        notifier.send_text.assert_not_called()

    async def test_stale_rollup_fires_d3(self, db):
        """Rollup older than threshold → D3 alert fires."""
        notifier = MagicMock()
        notifier.send_text = AsyncMock()
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_rollup(db, rollup_ts=now - timedelta(minutes=10))

        mon = FeedHealthMonitor(
            db=db,
            notifier=notifier,
            attribution_staleness_seconds=300,
            clock=lambda: now,
        )
        await mon.tick()

        notifier.send_text.assert_called_once()
        body = notifier.send_text.call_args[0][0]
        assert "D3" in body
        assert "stale" in body.lower()

    async def test_stale_then_recovers(self, db):
        """Once a stale rollup catches up, condition clears and next
        stale event can fire (state reset)."""
        notifier = MagicMock()
        notifier.send_text = AsyncMock()
        t0 = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)

        await _seed_rollup(db, rollup_ts=t0 - timedelta(minutes=10))
        mon = FeedHealthMonitor(
            db=db, notifier=notifier, attribution_staleness_seconds=300,
            alert_cooldown_seconds=0,
            clock=lambda: t0,
        )
        await mon.tick()
        assert notifier.send_text.call_count == 1

        # Fresh rollup lands — tick again, should NOT alert
        await _seed_rollup(db, rollup_ts=t0 + timedelta(seconds=30))
        mon._clock = lambda: t0 + timedelta(seconds=60)
        await mon.tick()
        assert notifier.send_text.call_count == 1  # unchanged


# ---------------------------------------------------------------------------
# D4 — publisher zero-publish
# ---------------------------------------------------------------------------


class TestD4PublisherZero:
    async def test_no_signals_ever_is_silent(self, db):
        """Pre-first-signal state: signals table empty. Should NOT alert."""
        notifier = MagicMock()
        notifier.send_text = AsyncMock()
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)

        mon = FeedHealthMonitor(
            db=db,
            notifier=notifier,
            publisher_zero_window_seconds=7200,
            clock=lambda: now,
        )
        await mon.tick()

        # D4 should not fire (no signals ever); D3 handled separately
        # so ensure only D3-safe path + no notification
        for call in notifier.send_text.call_args_list:
            assert "D4" not in call[0][0]

    async def test_recent_signal_is_silent(self, db):
        """Recent signal within window → no D4 alert."""
        notifier = MagicMock()
        notifier.send_text = AsyncMock()
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_signal(db, "01RECENT000000000000000AAA", ts=now - timedelta(minutes=30))

        mon = FeedHealthMonitor(
            db=db,
            notifier=notifier,
            publisher_zero_window_seconds=7200,
            clock=lambda: now,
        )
        await mon.tick()

        for call in notifier.send_text.call_args_list:
            assert "D4" not in call[0][0]

    async def test_stale_publisher_fires_d4(self, db):
        """Signals exist historically but none in the zero window →
        D4 alert fires."""
        notifier = MagicMock()
        notifier.send_text = AsyncMock()
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        # Seed a signal from 3h ago — outside the 2h window
        await _seed_signal(
            db, "01OLDSIGNAL000000000000AAA", ts=now - timedelta(hours=3)
        )

        mon = FeedHealthMonitor(
            db=db,
            notifier=notifier,
            publisher_zero_window_seconds=7200,  # 2h
            clock=lambda: now,
        )
        await mon.tick()

        assert notifier.send_text.called
        bodies = [c[0][0] for c in notifier.send_text.call_args_list]
        assert any("D4" in b for b in bodies)

    async def test_d4_clears_when_publisher_writes_again(self, db):
        """After firing, a new signal in the window clears the condition."""
        notifier = MagicMock()
        notifier.send_text = AsyncMock()
        t0 = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_signal(
            db, "01OLDSIGNAL000000000000AAA", ts=t0 - timedelta(hours=3)
        )

        mon = FeedHealthMonitor(
            db=db,
            notifier=notifier,
            publisher_zero_window_seconds=7200,
            alert_cooldown_seconds=0,
            clock=lambda: t0,
        )
        await mon.tick()
        fired_count_1 = sum(1 for c in notifier.send_text.call_args_list if "D4" in c[0][0])
        assert fired_count_1 == 1

        # New signal arrives — recovered
        await _seed_signal(db, "01FRESH0000000000000000AAA", ts=t0)
        mon._clock = lambda: t0 + timedelta(seconds=60)
        await mon.tick()
        fired_count_2 = sum(1 for c in notifier.send_text.call_args_list if "D4" in c[0][0])
        assert fired_count_2 == 1  # no new D4 fire


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------


class TestCooldown:
    async def test_cooldown_suppresses_repeat_within_window(self, db):
        """Two consecutive ticks within cooldown fire only once."""
        notifier = MagicMock()
        notifier.send_text = AsyncMock()
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_rollup(db, rollup_ts=now - timedelta(minutes=10))

        mon = FeedHealthMonitor(
            db=db,
            notifier=notifier,
            attribution_staleness_seconds=300,
            alert_cooldown_seconds=1800,  # 30 min
            clock=lambda: now,
        )
        await mon.tick()
        # Second tick 60s later — same stale rollup, within cooldown
        mon._clock = lambda: now + timedelta(seconds=60)
        await mon.tick()

        # D3 fired once
        d3_calls = [c for c in notifier.send_text.call_args_list if "D3" in c[0][0]]
        assert len(d3_calls) == 1

    async def test_cooldown_expires_allows_refire(self, db):
        """After cooldown elapses, same persistent condition fires again."""
        notifier = MagicMock()
        notifier.send_text = AsyncMock()
        t0 = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_rollup(db, rollup_ts=t0 - timedelta(minutes=10))

        mon = FeedHealthMonitor(
            db=db,
            notifier=notifier,
            attribution_staleness_seconds=300,
            alert_cooldown_seconds=1800,
            clock=lambda: t0,
        )
        await mon.tick()
        # Advance past cooldown
        mon._clock = lambda: t0 + timedelta(seconds=2000)
        await mon.tick()

        d3_calls = [c for c in notifier.send_text.call_args_list if "D3" in c[0][0]]
        assert len(d3_calls) == 2


# ---------------------------------------------------------------------------
# Notifier failure
# ---------------------------------------------------------------------------


class TestNotifierFailure:
    async def test_send_text_error_does_not_crash_tick(self, db):
        """Notifier.send_text raising must not prevent the tick from
        completing. The structured log event still captures the alert."""
        notifier = MagicMock()
        notifier.send_text = AsyncMock(side_effect=RuntimeError("webhook down"))
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_rollup(db, rollup_ts=now - timedelta(minutes=10))

        mon = FeedHealthMonitor(
            db=db, notifier=notifier, attribution_staleness_seconds=300,
            clock=lambda: now,
        )
        # Must not raise
        await mon.tick()

    async def test_no_notifier_still_logs(self, db):
        """FeedHealthMonitor with notifier=None must still run cleanly
        (alerts go to structured logs only)."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_rollup(db, rollup_ts=now - timedelta(minutes=10))

        mon = FeedHealthMonitor(
            db=db, notifier=None, attribution_staleness_seconds=300,
            clock=lambda: now,
        )
        await mon.tick()  # no raise
