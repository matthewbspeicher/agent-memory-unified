"""Integration test: FeedPublisher → feed_arb_signals → routes.

Wires the real EventBus, real FeedPublisher, and real FastAPI routes
against an in-memory SQLite DB. Emits an `arb.spread` event and verifies
the signal flows all the way through to both the subscriber API and
the public dashboard backend.

This is the end-to-end smoke per plan A10 — exercises the seam-in-mind
relocatability: publisher writes to a table, routes read from the same
table; no process-local state couples them.

Per feedback_integration_tests_mocked, integration tests must NOT be
mock-only. This one uses a real EventBus, real publisher loop (bounded
by .cancel), real SQLite DB, real FastAPI TestClient.

Run: cd /opt/agent-memory-unified && PYTHONPATH=.:trading \\
     trading/.venv/bin/python -m pytest trading/tests/integration/test_feeds_pipeline.py -v
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import feeds as feeds_route
from data.events import EventBus
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


def _spread_event(
    signal_id: str, *, gap_cents: float = 50.0, kalshi_cents: int = 70
):
    return {
        "signal_id": signal_id,
        "observation_id": 99,
        "kalshi_ticker": "KXINTEG-TEST",
        "poly_ticker": "0x" + "f" * 64,
        "kalshi_cents": kalshi_cents,
        "poly_cents": kalshi_cents - int(gap_cents),
        "gap_cents": gap_cents,
        "match_score": 0.85,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


class TestFeedPipeline:
    async def test_publisher_to_subscriber_api(self, db):
        """Publish one arb.spread on the real bus → verify subscriber
        API returns the shaped signal."""
        bus = EventBus()
        pub = FeedPublisher(db=db, event_bus=bus)

        # Run publisher in a background task bounded by cancel.
        task = asyncio.create_task(pub.run(), name="publisher_under_test")
        try:
            # Give the publisher one loop tick to subscribe.
            await asyncio.sleep(0.01)
            await bus.publish(
                "arb.spread",
                _spread_event("01INTEGTEST0000000000000001"),
            )
            # Wait for the row to land. The publisher processes events
            # off its queue sequentially; one event → one INSERT is fast
            # on in-memory SQLite.
            for _ in range(50):
                cursor = await db.execute(
                    "SELECT count(*) AS n FROM feed_arb_signals"
                )
                row = await cursor.fetchone()
                if int(row["n"]) >= 1:
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError("publisher never wrote a row")
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Now hit the subscriber API and verify the row comes back shaped.
        app = FastAPI()
        app.state.db = db
        app.state.redis = None
        app.include_router(feeds_route.router, prefix="/api/v1")

        # Bypass auth + scope gates (covered separately in unit tests).
        from api.auth import verify_api_key

        app.dependency_overrides[verify_api_key] = lambda: None
        for route in app.routes:
            for dep in getattr(route, "dependencies", []) or []:
                fn = getattr(dep, "dependency", None)
                if fn and "require_scope" in getattr(fn, "__qualname__", ""):
                    app.dependency_overrides[fn] = lambda: None

        client = TestClient(app)
        r = client.get(
            "/api/v1/feeds/arb/signals",
            params={"since": "2020-01-01T00:00:00Z"},
        )
        assert r.status_code == 200
        body = r.json()
        # Spec §3.2 shape: signals + next_since + truncated, no count field
        assert len(body["signals"]) == 1
        assert body["truncated"] is False
        s = body["signals"][0]
        assert s["signal_id"] == "01INTEGTEST0000000000000001"
        assert s["pair"]["kalshi"]["ticker"] == "KXINTEG-TEST"
        assert s["pair"]["kalshi"]["side"] == "SELL"  # gap>0 → sell kalshi
        assert s["pair"]["polymarket"]["side"] == "BUY"
        # next_since echoes the latest ts
        assert body["next_since"] == s["ts"]

    async def test_publisher_to_public_dashboard(self, db):
        """Same pipeline, public route end. Honest-tracker shape check."""
        bus = EventBus()
        pub = FeedPublisher(db=db, event_bus=bus)

        task = asyncio.create_task(pub.run(), name="publisher_public_test")
        try:
            await asyncio.sleep(0.01)
            for i in range(3):
                await bus.publish(
                    "arb.spread",
                    _spread_event(f"01INTEGPUBLIC00000000000{i:03d}", gap_cents=30 + i),
                )
            for _ in range(50):
                cursor = await db.execute(
                    "SELECT count(*) AS n FROM feed_arb_signals"
                )
                row = await cursor.fetchone()
                if int(row["n"]) >= 3:
                    break
                await asyncio.sleep(0.02)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        app = FastAPI()
        app.state.db = db
        app.state.redis = None
        app.include_router(feeds_route.router, prefix="/api/v1")
        client = TestClient(app)
        r = client.get("/api/v1/feeds/arb/public")
        assert r.status_code == 200
        body = r.json()
        assert len(body["signals"]) == 3
        # Spec §3.1: PnL can be null if no rollups yet.
        assert body["pnl"] is None
        # Public route shows newest-first (dashboard stream ordering,
        # per spec §3.1 "last 50 signals, newest first").
        ts_values = [s["ts"] for s in body["signals"]]
        assert ts_values == sorted(ts_values, reverse=True)
