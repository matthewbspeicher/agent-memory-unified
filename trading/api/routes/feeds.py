"""PM Arb Signal Feed API routes.

Two endpoints — both thin SELECT-and-shape over the feed_arb_signals /
feed_arb_pnl_rollup tables. Kept deliberately stateless (no in-process
caches, no DB triggers, no per-request DI container state) so the
handlers relocate cleanly to a separate web service when the local-first
host split happens per `project_local_first_direction`.

- GET /api/v1/feeds/arb/signals   (auth: read:feeds.arb)  — subscribers
- GET /api/v1/feeds/arb/public    (no auth)               — public dashboard

Spec: docs/superpowers/specs/2026-04-15-arb-signal-feed-design.md §3.2 + §3.1
Plan: ~/.claude/plans/temporal-spinning-flame.md A6 + A7
"""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.auth import verify_api_key
from api.identity.dependencies import require_scope
from utils.logging import log_event
from utils.metrics import (
    FEED_ARB_PUBLIC_CACHE_HITS_TOTAL,
    FEED_ARB_PUBLIC_CACHE_MISSES_TOTAL,
)

logger = logging.getLogger(__name__)


# Router is registered at /api/v1 prefix in app.py, yielding the spec paths.
# Subscriber endpoint has verify_api_key at the router level; the public
# endpoint overrides with dependencies=[] to skip auth.
router = APIRouter(prefix="/feeds/arb", tags=["feeds"])


# ---------------------------------------------------------------------------
# Public dashboard — GET /api/v1/feeds/arb/public
# ---------------------------------------------------------------------------

# Cache TTL in seconds. 10s per spec §3.1 ("updates every ~10s"). A dashboard
# tab open in 100 browsers at 10s cadence produces at most 6 DB reads/min
# with cache hit ratio >98% — the plan's G4 acceptance.
PUBLIC_CACHE_TTL_SECONDS = 10

# Cache key prefix. Keep short to bound Redis memory even if we add dimensions.
_PUBLIC_CACHE_KEY = "feed:arb:public:v1"

# Last-50 signals window. Spec §3.1: "Live signal stream (last 50 signals)".
PUBLIC_SIGNAL_LIMIT = 50


@router.get("/public", dependencies=[])
async def public_dashboard_snapshot(request: Request) -> dict[str, Any]:
    """Anonymized public dashboard feed: last N signals + latest PnL rollup.

    Unauthenticated on purpose — this drives remembr.dev/feeds/arb/live
    which needs to be indexable and shareable. Redis-backed cache with
    10s TTL absorbs dashboard-spike traffic (see spec §3.1).

    Response shape (keep compatible with spec §3.1):
        {
            "as_of": <iso8601>,
            "signals": [{signal_id, ts, pair, edge_cents, ...}, ...],  # last 50
            "pnl": {realized_usd, open_usd, cumulative_usd,
                    open_positions, closed_positions} | null,
            "scaling": <str> | null  # e.g. "assumes 10x capital vs $11k sleeve"
        }
    """
    redis = getattr(request.app.state, "redis", None)

    if redis is not None:
        try:
            cached = await redis.get(_PUBLIC_CACHE_KEY)
        except Exception as exc:
            # Redis hiccup — log once and fall through to DB. Don't fail
            # the request; the public dashboard's "honest tracker" brand
            # dies if we 5xx.
            log_event(
                logger,
                logging.WARNING,
                "error",
                "feeds.public: redis.get failed (falling back to DB): %s" % exc,
                data={"component": "feeds_public", "exception_type": type(exc).__name__},
            )
            cached = None
        if cached is not None:
            FEED_ARB_PUBLIC_CACHE_HITS_TOTAL.inc()
            try:
                return json.loads(cached)
            except Exception:
                # Corrupted cache entry — drop it and recompute.
                try:
                    await redis.delete(_PUBLIC_CACHE_KEY)
                except Exception:
                    pass

    FEED_ARB_PUBLIC_CACHE_MISSES_TOTAL.inc()
    db = request.app.state.db
    signals = await _select_recent_signals(db, limit=PUBLIC_SIGNAL_LIMIT)
    pnl = await _select_latest_pnl(db)
    snapshot = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "signals": signals,
        "pnl": pnl,
        "scaling": (pnl or {}).get("scaling_assumption") if pnl else None,
    }

    if redis is not None:
        try:
            await redis.set(
                _PUBLIC_CACHE_KEY,
                json.dumps(snapshot, default=_json_default),
                ex=PUBLIC_CACHE_TTL_SECONDS,
            )
        except Exception as exc:
            # Cache fill failure is non-fatal — next request re-fills.
            log_event(
                logger,
                logging.WARNING,
                "error",
                "feeds.public: redis.set failed (serving uncached): %s" % exc,
                data={"component": "feeds_public", "exception_type": type(exc).__name__},
            )

    return snapshot


# ---------------------------------------------------------------------------
# Subscriber API — GET /api/v1/feeds/arb/signals
# ---------------------------------------------------------------------------


@router.get(
    "/signals",
    dependencies=[Depends(verify_api_key), Depends(require_scope("read:feeds.arb"))],
)
async def subscriber_signal_feed(
    request: Request,
    since: str = Query(
        ...,
        description="ISO-8601 timestamp. Returns signals with ts >= since.",
        examples=["2026-04-15T14:30:00Z"],
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Max signals to return per request. Spec §3.2 max=500.",
    ),
) -> dict[str, Any]:
    """Paid-tier signal feed — requires read:feeds.arb scope.

    Returns JSON matching spec §3.2: `signals`, `next_since`, `truncated`.
    Rate-limited by the existing tier system (60/min agent tier by
    default; no new tier in week 0).

    Stateless by design: no app-state caching in the handler, so this
    route can relocate to a separate web service under
    project_local_first_direction without rewrite.
    """
    try:
        since_dt = _parse_iso(since)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid 'since' timestamp: {since!r}. Expected ISO-8601.",
        )

    db = request.app.state.db
    # Spec §3.2 returns signals OLDEST first within the since window, so
    # a client advancing `since` picks up seamlessly. We query newest-first
    # from the DB (index hits idx_feed_arb_signals_ts DESC) and reverse
    # after the limit clip — a common paged-feed pattern.
    signals = await _select_signals_since(db, since=since_dt, limit=limit)
    signals_asc = list(reversed(signals))

    # Per spec §3.2:
    #   - truncated = True when response hit `limit` (client re-polls)
    #   - next_since = latest returned ts if not empty, else echoes `since`
    truncated = len(signals_asc) >= limit
    next_since = signals_asc[-1]["ts"] if signals_asc else since

    return {
        "signals": signals_asc,
        "next_since": next_since,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# SQL helpers — dual-path SQLite (tests) + Postgres (prod)
# ---------------------------------------------------------------------------
#
# Same pattern used elsewhere: Postgres has `fetchone`/`fetchall` on the
# wrapper, SQLite (aiosqlite) returns a Cursor from `execute()`. Keep the
# helpers single-purpose so the handler above stays shape-only.


async def _select_signals_since(
    db: Any, *, since: datetime, limit: int
) -> list[dict[str, Any]]:
    """SELECT signals with ts >= since, newest first, capped at limit."""
    is_postgres = hasattr(db, "fetchall")
    since_param: Any = since if is_postgres else since.isoformat()
    sql = (
        "SELECT signal_id, ts, pair_kalshi_ticker, pair_kalshi_side, "
        "       pair_poly_token_id, pair_poly_side, edge_cents, "
        "       max_size_at_edge_usd, expires_at, outcome "
        "FROM feed_arb_signals "
        "WHERE ts >= ? "
        "ORDER BY ts DESC "
        "LIMIT ?"
    )
    rows = await _rows(db, sql, (since_param, limit))
    return [_shape_signal_row(r) for r in rows]


async def _select_recent_signals(db: Any, *, limit: int) -> list[dict[str, Any]]:
    """SELECT last N signals regardless of ts, newest first."""
    sql = (
        "SELECT signal_id, ts, pair_kalshi_ticker, pair_kalshi_side, "
        "       pair_poly_token_id, pair_poly_side, edge_cents, "
        "       max_size_at_edge_usd, expires_at, outcome "
        "FROM feed_arb_signals "
        "ORDER BY ts DESC "
        "LIMIT ?"
    )
    rows = await _rows(db, sql, (limit,))
    return [_shape_signal_row(r) for r in rows]


async def _select_latest_pnl(db: Any) -> dict[str, Any] | None:
    """Most recent feed_arb_pnl_rollup row, or None if no rollups yet."""
    sql = (
        "SELECT rollup_ts, realized_pnl_usd, open_pnl_usd, cumulative_pnl_usd, "
        "       open_position_count, closed_position_count, "
        "       scaled_realized_pnl_usd, scaled_open_pnl_usd, "
        "       scaled_cumulative_pnl_usd, scaling_assumption "
        "FROM feed_arb_pnl_rollup "
        "ORDER BY rollup_ts DESC "
        "LIMIT 1"
    )
    rows = await _rows(db, sql, ())
    if not rows:
        return None
    r = rows[0]
    return {
        "rollup_ts": _iso(r["rollup_ts"]),
        "realized_usd": _num(r["realized_pnl_usd"]),
        "open_usd": _num(r["open_pnl_usd"]),
        "cumulative_usd": _num(r["cumulative_pnl_usd"]),
        "open_positions": int(r["open_position_count"]),
        "closed_positions": int(r["closed_position_count"]),
        "scaled_realized_usd": _num(r["scaled_realized_pnl_usd"]),
        "scaled_open_usd": _num(r["scaled_open_pnl_usd"]),
        "scaled_cumulative_usd": _num(r["scaled_cumulative_pnl_usd"]),
        "scaling_assumption": r["scaling_assumption"],
    }


async def _rows(db: Any, sql: str, params: tuple) -> list[dict[str, Any]]:
    """Cross-backend SELECT. Returns a list of dict-like rows."""
    if hasattr(db, "fetchall"):
        # PostgresDB wrapper
        return list(await db.fetchall(sql, params))
    # aiosqlite
    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


def _shape_signal_row(r: dict[str, Any]) -> dict[str, Any]:
    """Format a DB row for the spec §3.2 response shape.

    Groups the kalshi/poly legs under a `pair` object so the subscriber
    can deserialize into a compact value type. Strips internal columns
    (raw_signal, outcome_set_at) from the subscriber-facing payload.
    """
    return {
        "signal_id": r["signal_id"],
        "ts": _iso(r["ts"]),
        "pair": {
            "kalshi": {
                "ticker": r["pair_kalshi_ticker"],
                "side": r["pair_kalshi_side"],
            },
            "polymarket": {
                "token_id": r["pair_poly_token_id"],
                "side": r["pair_poly_side"],
            },
        },
        "edge_cents": _num(r["edge_cents"]),
        # Per spec §3.2 — the orderbook-depth estimate, not a recommended
        # position size. v1 publisher uses a conservative constant until
        # live orderbook depth is threaded onto the arb.spread event.
        "max_size_at_edge_usd": _num(r["max_size_at_edge_usd"]),
        "expires_at": _iso(r["expires_at"]),
        "outcome": r["outcome"],
    }


# ---------------------------------------------------------------------------
# Coercers
# ---------------------------------------------------------------------------


def _iso(v: Any) -> str | None:
    """Coerce a ts column value (datetime on Postgres, str on SQLite) to ISO."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def _num(v: Any) -> float | None:
    """Coerce a NUMERIC/REAL column (Decimal, float, str) to float for JSON."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _parse_iso(s: str) -> datetime:
    """Parse ISO-8601 with 'Z' and naive-datetime tolerance."""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception as exc:
        raise ValueError(f"Invalid ISO timestamp: {s!r}") from exc


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    from decimal import Decimal

    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
