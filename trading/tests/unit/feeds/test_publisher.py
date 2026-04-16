"""Unit tests for FeedPublisher (A4).

Covers: happy path INSERT, CostModel gate rejection, missing-signal_id drop,
dedup by PRIMARY KEY, side derivation from gap sign, raw_signal forensics
payload shape, DB-error swallow-with-log.

SQLite in-memory is the DB under test — the publisher is DB-agnostic
(uses `?` placeholders that translate to `$N` on Postgres per
storage/postgres.py:_convert_placeholders).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from execution.cost_model import CostModel
from feeds.publisher import FeedPublisher
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


@pytest.fixture
def cost_model():
    # Default CostModel — realistic fees. The gate passes for reasonably
    # large gaps and fails for tiny ones.
    return CostModel()


class _FakeBus:
    """Minimal EventBus stand-in: yields a scripted sequence then stops."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = list(events)

    async def subscribe(self):
        for ev in self._events:
            yield ev


def _event(
    *,
    signal_id: str = "01TESTSIGNAL00000000000001",
    gap_cents: float = 50.0,
    kalshi_ticker: str = "KXELEC-TEST",
    poly_ticker: str = "0x" + "a" * 64,
    observed_at: str = "2026-04-16T14:00:00+00:00",
    kalshi_cents: int = 60,
    poly_cents: int = 10,
) -> dict[str, Any]:
    return {
        "topic": "arb.spread",
        "data": {
            "signal_id": signal_id,
            "observation_id": 1,
            "kalshi_ticker": kalshi_ticker,
            "poly_ticker": poly_ticker,
            "kalshi_cents": kalshi_cents,
            "poly_cents": poly_cents,
            "gap_cents": gap_cents,
            "match_score": 0.9,
            "observed_at": observed_at,
        },
    }


async def _count_rows(db, signal_id: str | None = None) -> int:
    if signal_id is None:
        cursor = await db.execute("SELECT count(*) AS n FROM feed_arb_signals")
    else:
        cursor = await db.execute(
            "SELECT count(*) AS n FROM feed_arb_signals WHERE signal_id = ?",
            (signal_id,),
        )
    row = await cursor.fetchone()
    return int(row["n"])


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestFeedPublisherHappyPath:
    async def test_publishes_qualifying_signal(self, db, cost_model):
        bus = _FakeBus([_event()])
        pub = FeedPublisher(
            db=db, event_bus=bus, cost_model=cost_model, min_profit_bps=5.0
        )
        await pub.run()  # drains the scripted bus and returns

        assert await _count_rows(db, "01TESTSIGNAL00000000000001") == 1

    async def test_row_columns_populated(self, db, cost_model):
        bus = _FakeBus([_event()])
        await FeedPublisher(db=db, event_bus=bus, cost_model=cost_model).run()

        cursor = await db.execute(
            "SELECT signal_id, ts, pair_kalshi_ticker, pair_kalshi_side, "
            "       pair_poly_token_id, pair_poly_side, edge_cents, "
            "       max_size_at_edge_usd, expires_at, outcome, raw_signal "
            "FROM feed_arb_signals"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["signal_id"] == "01TESTSIGNAL00000000000001"
        assert row["ts"].startswith("2026-04-16T14:00:00")
        assert row["pair_kalshi_ticker"] == "KXELEC-TEST"
        assert row["pair_poly_token_id"].startswith("0x")
        assert row["edge_cents"] > 0  # net of fees
        assert row["max_size_at_edge_usd"] > 0
        assert row["expires_at"] > row["ts"]
        assert row["outcome"] is None  # set later by attribution

    async def test_raw_signal_is_valid_json_with_computed_fields(self, db, cost_model):
        bus = _FakeBus([_event()])
        await FeedPublisher(db=db, event_bus=bus, cost_model=cost_model).run()

        cursor = await db.execute("SELECT raw_signal FROM feed_arb_signals")
        row = await cursor.fetchone()
        payload = json.loads(row["raw_signal"])
        assert payload["signal_id"] == "01TESTSIGNAL00000000000001"
        assert "_computed" in payload
        assert "edge_cents" in payload["_computed"]
        assert "kalshi_side" in payload["_computed"]
        assert "poly_side" in payload["_computed"]


# ---------------------------------------------------------------------------
# Gate — CostModel.should_execute
# ---------------------------------------------------------------------------


class TestFeedPublisherGate:
    async def test_drops_below_min_profit_bps(self, db, cost_model):
        # Tiny 1¢ gap — cannot cover realistic fees.
        bus = _FakeBus([_event(gap_cents=1.0, kalshi_cents=51, poly_cents=50)])
        pub = FeedPublisher(
            db=db, event_bus=bus, cost_model=cost_model, min_profit_bps=5.0
        )
        await pub.run()

        assert await _count_rows(db) == 0

    async def test_publishes_when_gate_is_zero(self, db):
        # With a zero-fee CostModel any positive gap passes.
        class _ZeroCost(CostModel):
            def expected_profit_bps(self, gap_cents, slippage_bps=None):
                return Decimal(str(float(gap_cents) * 100))  # gap in bps
            def should_execute(self, gap_cents, min_profit_bps=0.0, slippage_bps=None):
                return float(gap_cents) > 0

        bus = _FakeBus([_event(gap_cents=2.0, kalshi_cents=52, poly_cents=50)])
        pub = FeedPublisher(
            db=db, event_bus=bus, cost_model=_ZeroCost(), min_profit_bps=0.0
        )
        await pub.run()

        assert await _count_rows(db) == 1


# ---------------------------------------------------------------------------
# Defensive — malformed events
# ---------------------------------------------------------------------------


class TestFeedPublisherDefensive:
    async def test_missing_signal_id_dropped(self, db, cost_model):
        evt = _event()
        del evt["data"]["signal_id"]
        bus = _FakeBus([evt])
        await FeedPublisher(db=db, event_bus=bus, cost_model=cost_model).run()

        assert await _count_rows(db) == 0

    async def test_missing_tickers_dropped(self, db, cost_model):
        evt = _event(kalshi_ticker="")
        bus = _FakeBus([evt])
        await FeedPublisher(db=db, event_bus=bus, cost_model=cost_model).run()

        assert await _count_rows(db) == 0

    async def test_non_arb_spread_topic_ignored(self, db, cost_model):
        evt = _event()
        evt["topic"] = "arb.shadow"  # different topic
        bus = _FakeBus([evt])
        await FeedPublisher(db=db, event_bus=bus, cost_model=cost_model).run()

        assert await _count_rows(db) == 0

    async def test_handler_crash_does_not_break_subscription(self, db, cost_model):
        # Force _maybe_publish to crash on first event, then verify a
        # subsequent well-formed event is still processed.
        pub = FeedPublisher(db=db, event_bus=None, cost_model=cost_model)  # bus set below

        original = pub._maybe_publish
        calls = {"n": 0}

        async def flaky(data):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("simulated bug")
            return await original(data)

        pub._maybe_publish = flaky
        pub._bus = _FakeBus([_event(signal_id="01BADFIRST000000000000001"), _event()])
        await pub.run()

        # Second event should have made it through.
        assert await _count_rows(db, "01BADFIRST000000000000001") == 0
        assert await _count_rows(db, "01TESTSIGNAL00000000000001") == 1


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


class TestFeedPublisherDedup:
    async def test_duplicate_signal_id_is_noop(self, db, cost_model):
        e1 = _event(signal_id="01DEDUP000000000000000000A")
        e2 = _event(signal_id="01DEDUP000000000000000000A")  # same id
        bus = _FakeBus([e1, e2])
        await FeedPublisher(db=db, event_bus=bus, cost_model=cost_model).run()

        assert await _count_rows(db, "01DEDUP000000000000000000A") == 1

    async def test_different_signal_ids_both_land(self, db, cost_model):
        bus = _FakeBus(
            [
                _event(signal_id="01FIRST000000000000000000A"),
                _event(signal_id="01SECOND00000000000000000A"),
            ]
        )
        await FeedPublisher(db=db, event_bus=bus, cost_model=cost_model).run()

        assert await _count_rows(db) == 2


# ---------------------------------------------------------------------------
# Side derivation
# ---------------------------------------------------------------------------


class TestFeedPublisherSides:
    async def test_positive_gap_kalshi_sells_poly_buys(self, db, cost_model):
        # Kalshi more expensive than Polymarket → sell Kalshi, buy Poly.
        bus = _FakeBus([_event(gap_cents=50.0, kalshi_cents=70, poly_cents=20)])
        await FeedPublisher(db=db, event_bus=bus, cost_model=cost_model).run()

        cursor = await db.execute(
            "SELECT pair_kalshi_side, pair_poly_side FROM feed_arb_signals"
        )
        row = await cursor.fetchone()
        assert row["pair_kalshi_side"] == "SELL"
        assert row["pair_poly_side"] == "BUY"

    async def test_negative_gap_kalshi_buys_poly_sells(self, db, cost_model):
        # Polymarket more expensive → buy Kalshi, sell Poly. Feed sees
        # gap_cents=-50; use a zero-cost model since our sample gap is
        # negative. (In practice the producer emits abs value; this exercises
        # the derivation logic defensively.)
        class _ZeroCost(CostModel):
            def should_execute(self, gap_cents, min_profit_bps=0.0, slippage_bps=None):
                return abs(float(gap_cents)) > 0

        bus = _FakeBus([_event(gap_cents=-50.0, kalshi_cents=20, poly_cents=70)])
        await FeedPublisher(
            db=db, event_bus=bus, cost_model=_ZeroCost(), min_profit_bps=0.0
        ).run()

        cursor = await db.execute(
            "SELECT pair_kalshi_side, pair_poly_side FROM feed_arb_signals"
        )
        row = await cursor.fetchone()
        assert row["pair_kalshi_side"] == "BUY"
        assert row["pair_poly_side"] == "SELL"


# ---------------------------------------------------------------------------
# DB failure — swallow + log
# ---------------------------------------------------------------------------


class TestFeedPublisherDBFailure:
    async def test_db_execute_error_swallowed(self, cost_model):
        # Replace the DB connection with a mock whose execute raises. The
        # publisher should NOT propagate — D4 will alert via the structured
        # `error` event_type instead.
        bad_db = AsyncMock()
        bad_db.execute.side_effect = RuntimeError("db down")
        bad_db.commit = AsyncMock()
        bus = _FakeBus([_event()])
        pub = FeedPublisher(db=bad_db, event_bus=bus, cost_model=cost_model)

        # Completes without raising.
        await pub.run()

        bad_db.execute.assert_called_once()
