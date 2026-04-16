"""Unit tests for /api/v1/feeds/arb/{signals,public} routes (A6 + A7).

Covers:
- Subscriber route: scope gate, shape per spec §3.2, since/limit parsing,
  invalid `since` returns 400, empty results shape.
- Public route: no-auth open, cache hit/miss increments counters,
  Redis outage falls back to DB gracefully.
- Shared: SQLite vs Postgres path (tests use in-memory SQLite).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import feeds as feeds_route
from storage.db import init_db


# ---------------------------------------------------------------------------
# Test app + DB fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


@pytest.fixture
async def db_with_signals(db):
    """Seed feed_arb_signals with three signals spanning two timestamps."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        (
            "01SIGOLD00000000000000000A",
            (now - timedelta(hours=2)).isoformat(),
            "KXOLD",
            "SELL",
            "0xpolyOLD",
            "BUY",
            3.5,
            100.0,
            (now - timedelta(hours=2) + timedelta(minutes=5)).isoformat(),
            json.dumps({"signal_id": "01SIGOLD00000000000000000A"}),
        ),
        (
            "01SIGMID00000000000000000B",
            (now - timedelta(hours=1)).isoformat(),
            "KXMID",
            "SELL",
            "0xpolyMID",
            "BUY",
            10.0,
            150.0,
            (now - timedelta(hours=1) + timedelta(minutes=5)).isoformat(),
            json.dumps({"signal_id": "01SIGMID00000000000000000B"}),
        ),
        (
            "01SIGNEW00000000000000000C",
            now.isoformat(),
            "KXNEW",
            "BUY",
            "0xpolyNEW",
            "SELL",
            20.0,
            200.0,
            (now + timedelta(minutes=5)).isoformat(),
            json.dumps({"signal_id": "01SIGNEW00000000000000000C"}),
        ),
    ]
    for r in rows:
        await db.execute(
            "INSERT INTO feed_arb_signals "
            "(signal_id, ts, pair_kalshi_ticker, pair_kalshi_side, "
            " pair_poly_token_id, pair_poly_side, edge_cents, "
            " max_size_at_edge_usd, expires_at, raw_signal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            r,
        )
    await db.commit()
    return db, now


class _FakeRedis:
    """In-memory stand-in for redis.asyncio.Redis `get`/`set`/`delete`."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


def _make_app(db, redis=None, *, skip_auth: bool = True, has_scope: bool = True):
    """Build a FastAPI app with the feeds router, with auth + scope deps
    dependency-overridden for testability.

    require_scope(s) returns a freshly-built closure each call, so the
    closure in the registered route's Depends list is NOT the same object
    the test can rebuild. Walk the router's routes to find it and override
    that specific callable.
    """
    app = FastAPI()
    app.state.db = db
    app.state.redis = redis
    app.include_router(feeds_route.router, prefix="/api/v1")

    if skip_auth:
        from api.auth import verify_api_key

        app.dependency_overrides[verify_api_key] = lambda: None

    async def _permit_all():
        if not has_scope:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Forbidden (test)")
        return None

    # Walk every registered route and replace any `require_scope`-produced
    # checker (its __qualname__ includes "require_scope.<locals>.checker")
    # with our pass-through. This matches whatever scope strings the route
    # uses without hardcoding them in the test.
    for route in app.routes:
        for dep in getattr(route, "dependencies", []) or []:
            fn = getattr(dep, "dependency", None)
            if fn is None:
                continue
            qn = getattr(fn, "__qualname__", "")
            if "require_scope" in qn:
                app.dependency_overrides[fn] = _permit_all

    return app


# ---------------------------------------------------------------------------
# Subscriber route — GET /api/v1/feeds/arb/signals
# ---------------------------------------------------------------------------


class TestSubscriberRoute:
    def test_returns_spec_shape(self, db_with_signals):
        db, now = db_with_signals
        client = TestClient(_make_app(db))
        r = client.get(
            "/api/v1/feeds/arb/signals",
            params={"since": "2020-01-01T00:00:00Z", "limit": 100},
        )
        assert r.status_code == 200
        body = r.json()
        # Spec §3.2 top-level shape
        assert set(body.keys()) >= {"signals", "next_since", "truncated"}
        assert len(body["signals"]) == 3
        s = body["signals"][0]
        # Spec §3.2 row shape
        assert set(s.keys()) >= {
            "signal_id",
            "ts",
            "pair",
            "edge_cents",
            "max_size_at_edge_usd",
            "expires_at",
        }
        assert set(s["pair"].keys()) == {"kalshi", "polymarket"}
        assert set(s["pair"]["kalshi"].keys()) == {"ticker", "side"}
        assert set(s["pair"]["polymarket"].keys()) == {"token_id", "side"}

    def test_oldest_first_for_paging(self, db_with_signals):
        """Spec §3.2: client advances `since` from the latest returned ts,
        so signals are returned oldest-first."""
        db, _ = db_with_signals
        client = TestClient(_make_app(db))
        r = client.get(
            "/api/v1/feeds/arb/signals",
            params={"since": "2020-01-01T00:00:00Z"},
        )
        ids = [s["signal_id"] for s in r.json()["signals"]]
        assert ids == [
            "01SIGOLD00000000000000000A",
            "01SIGMID00000000000000000B",
            "01SIGNEW00000000000000000C",
        ]

    def test_next_since_echoes_latest_ts_when_not_truncated(self, db_with_signals):
        db, _ = db_with_signals
        client = TestClient(_make_app(db))
        r = client.get(
            "/api/v1/feeds/arb/signals",
            params={"since": "2020-01-01T00:00:00Z", "limit": 100},
        )
        body = r.json()
        assert body["truncated"] is False
        # next_since is the latest (last, in ascending order) ts
        assert body["next_since"] == body["signals"][-1]["ts"]

    def test_next_since_echoes_since_when_empty(self, db):
        client = TestClient(_make_app(db))
        r = client.get(
            "/api/v1/feeds/arb/signals",
            params={"since": "2030-01-01T00:00:00Z"},
        )
        body = r.json()
        assert body["signals"] == []
        assert body["truncated"] is False
        assert body["next_since"] == "2030-01-01T00:00:00Z"

    def test_truncated_true_when_limit_hit(self, db_with_signals):
        db, _ = db_with_signals
        client = TestClient(_make_app(db))
        r = client.get(
            "/api/v1/feeds/arb/signals",
            params={"since": "2020-01-01T00:00:00Z", "limit": 1},
        )
        body = r.json()
        assert len(body["signals"]) == 1
        assert body["truncated"] is True

    def test_since_filter(self, db_with_signals):
        db, now = db_with_signals
        client = TestClient(_make_app(db))
        # Cut off at 90 minutes ago → only MID and NEW should come back
        since = (now - timedelta(minutes=90)).isoformat()
        r = client.get(
            "/api/v1/feeds/arb/signals", params={"since": since, "limit": 100}
        )
        ids = [s["signal_id"] for s in r.json()["signals"]]
        assert ids == [
            "01SIGMID00000000000000000B",
            "01SIGNEW00000000000000000C",
        ]

    def test_invalid_since_returns_400(self, db_with_signals):
        db, _ = db_with_signals
        client = TestClient(_make_app(db))
        r = client.get(
            "/api/v1/feeds/arb/signals", params={"since": "not-a-date"}
        )
        assert r.status_code == 400

    def test_scope_rejection_returns_403(self, db_with_signals):
        db, _ = db_with_signals
        client = TestClient(_make_app(db, has_scope=False))
        r = client.get(
            "/api/v1/feeds/arb/signals",
            params={"since": "2020-01-01T00:00:00Z"},
        )
        assert r.status_code == 403

    def test_limit_over_500_rejected(self, db_with_signals):
        db, _ = db_with_signals
        client = TestClient(_make_app(db))
        r = client.get(
            "/api/v1/feeds/arb/signals",
            params={"since": "2020-01-01T00:00:00Z", "limit": 9999},
        )
        # FastAPI Query validator returns 422
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Public route — GET /api/v1/feeds/arb/public
# ---------------------------------------------------------------------------


class TestPublicRoute:
    def test_open_no_auth(self, db_with_signals):
        db, _ = db_with_signals
        # No auth override needed; the route has dependencies=[] on purpose.
        app = FastAPI()
        app.state.db = db
        app.state.redis = None
        app.include_router(feeds_route.router, prefix="/api/v1")
        client = TestClient(app)
        r = client.get("/api/v1/feeds/arb/public")
        assert r.status_code == 200
        assert "signals" in r.json()
        assert "pnl" in r.json()

    def test_cache_hit_second_call(self, db_with_signals):
        db, _ = db_with_signals
        redis = _FakeRedis()
        app = FastAPI()
        app.state.db = db
        app.state.redis = redis
        app.include_router(feeds_route.router, prefix="/api/v1")
        client = TestClient(app)

        # Miss
        r1 = client.get("/api/v1/feeds/arb/public")
        assert r1.status_code == 200

        # Hit — body comes from cache (still 200 + same shape)
        r2 = client.get("/api/v1/feeds/arb/public")
        assert r2.status_code == 200
        # Second call's `as_of` is the cached one (first call's), proving
        # the handler didn't recompute.
        assert r1.json()["as_of"] == r2.json()["as_of"]

    def test_redis_outage_falls_back_to_db(self, db_with_signals):
        db, _ = db_with_signals

        # Redis that raises on get — must not propagate.
        class _BadRedis:
            async def get(self, *a, **kw):
                raise RuntimeError("redis down")

            async def set(self, *a, **kw):
                raise RuntimeError("redis down")

            async def delete(self, *a, **kw):
                pass

        app = FastAPI()
        app.state.db = db
        app.state.redis = _BadRedis()
        app.include_router(feeds_route.router, prefix="/api/v1")
        client = TestClient(app)
        r = client.get("/api/v1/feeds/arb/public")
        assert r.status_code == 200
        body = r.json()
        assert len(body["signals"]) == 3

    def test_limits_to_public_window(self, db_with_signals):
        db, _ = db_with_signals
        app = FastAPI()
        app.state.db = db
        app.state.redis = None
        app.include_router(feeds_route.router, prefix="/api/v1")
        client = TestClient(app)
        r = client.get("/api/v1/feeds/arb/public")
        # We only seeded 3 rows, so the 50-row cap doesn't clip here.
        # But the count shouldn't exceed PUBLIC_SIGNAL_LIMIT.
        assert len(r.json()["signals"]) <= feeds_route.PUBLIC_SIGNAL_LIMIT

    def test_empty_tables_returns_empty_signals_and_null_pnl(self, db):
        app = FastAPI()
        app.state.db = db
        app.state.redis = None
        app.include_router(feeds_route.router, prefix="/api/v1")
        client = TestClient(app)
        r = client.get("/api/v1/feeds/arb/public")
        assert r.status_code == 200
        body = r.json()
        assert body["signals"] == []
        assert body["pnl"] is None
