"""FeedPublisher — writes arb signals to feed_arb_signals.

Subscribes to the existing `EventBus` topic `arb.spread` (produced by
`strategies/cross_platform_arb.py` and already consumed by
`execution/arb_executor.py`), re-applies the same `CostModel.should_execute`
gate the executor uses, and persists qualifying signals to
`feed_arb_signals` so the paid-subscriber API and public dashboard
can serve them.

The publisher runs in scan-only mode (no trades placed). It does not
touch order execution or shadow decisions — those stay with `ArbExecutor`.

Spec: docs/superpowers/specs/2026-04-15-arb-signal-feed-design.md §3.2, §4.1
Plan: ~/.claude/plans/temporal-spinning-flame.md A4
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from execution.cost_model import CostModel
from utils.logging import log_event
from utils.metrics import (
    FEED_ARB_SIGNALS_DROPPED_TOTAL,
    FEED_ARB_SIGNALS_PUBLISHED_TOTAL,
)

if TYPE_CHECKING:
    from data.events import EventBus


logger = logging.getLogger(__name__)


# Default expiration window for an arb signal after emission. Arb spreads
# are short-lived; a subscriber polling every 30s has at most ~10 chances
# to act on a signal before we declare it stale. The attribution job uses
# this to mark `outcome = 'missed'` when nothing filled in time.
DEFAULT_EXPIRATION_SECONDS = 300  # 5 minutes

# Conservative v1 size hint. Without live orderbook depth on the event
# payload we cannot compute "max USD notional at this edge" precisely —
# so we report a round-number floor. Attribution-job feedback (what
# actually filled vs what we advertised) will calibrate this later.
DEFAULT_MAX_SIZE_USD = Decimal("100.00")


class FeedPublisher:
    """Subscribes to `arb.spread` and persists qualifying signals.

    Dedicated background task; one publisher per engine process. Deduplicates
    on `signal_id` PRIMARY KEY at the DB layer (ON CONFLICT DO NOTHING) —
    the producer strategy already mints ULIDs per candidate so duplicate
    emissions of the same underlying observation are rare.
    """

    def __init__(
        self,
        db: Any,
        event_bus: EventBus,
        cost_model: CostModel | None = None,
        min_profit_bps: float = 5.0,
        default_expiration_seconds: int = DEFAULT_EXPIRATION_SECONDS,
        default_max_size_usd: Decimal | float = DEFAULT_MAX_SIZE_USD,
    ) -> None:
        self._db = db
        self._bus = event_bus
        self._cost_model = cost_model or CostModel()
        self._min_profit_bps = float(min_profit_bps)
        self._expiration_seconds = int(default_expiration_seconds)
        self._max_size_usd = Decimal(str(default_max_size_usd))

    # ------------------------------------------------------------------
    # Background-task entry point (registered by app.py lifespan)
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Subscribe to arb.spread events and persist qualifying signals."""
        logger.info(
            "FeedPublisher: starting (min_profit_bps=%.1f, expiration=%ds)",
            self._min_profit_bps,
            self._expiration_seconds,
        )
        async for event in self._bus.subscribe():
            if event.get("topic") != "arb.spread":
                continue
            try:
                await self._maybe_publish(event.get("data", {}))
            except Exception as exc:
                # Any uncaught error in the inner handler is a bug — log it
                # with enough structure for the D4 alert to catch. Do NOT
                # return / break: keep the subscription alive so a single
                # bad event doesn't take the publisher down.
                log_event(
                    logger,
                    logging.ERROR,
                    "error",
                    "FeedPublisher._maybe_publish crashed: %s" % exc,
                    data={
                        "component": "feed_publisher",
                        "exception_type": type(exc).__name__,
                        "event_keys": list((event.get("data") or {}).keys()),
                    },
                    exc_info=True,
                )
                FEED_ARB_SIGNALS_DROPPED_TOTAL.labels(reason="store_error").inc()

    # ------------------------------------------------------------------
    # Event → row
    # ------------------------------------------------------------------

    async def _maybe_publish(self, data: dict[str, Any]) -> None:
        """Apply the profit-gate, derive row shape, and INSERT."""
        signal_id = data.get("signal_id")
        if not signal_id:
            # Every producer minted-ULID path must populate signal_id. If it's
            # missing, upstream regressed — don't silently write a row with a
            # synthesized id, we would lose attribution. Log and drop.
            FEED_ARB_SIGNALS_DROPPED_TOTAL.labels(reason="missing_signal_id").inc()
            log_event(
                logger,
                logging.WARNING,
                "error",
                "FeedPublisher: dropped arb.spread with no signal_id",
                data={"component": "feed_publisher", "event_keys": list(data.keys())},
            )
            return

        kalshi_ticker = data.get("kalshi_ticker", "")
        poly_ticker = data.get("poly_ticker", "")
        if not kalshi_ticker or not poly_ticker:
            FEED_ARB_SIGNALS_DROPPED_TOTAL.labels(reason="missing_tickers").inc()
            return

        gap_cents = float(data.get("gap_cents", 0) or 0)
        kalshi_cents = data.get("kalshi_cents")
        poly_cents = data.get("poly_cents")

        # Same gate ArbExecutor uses. Signals that wouldn't cover fees and
        # slippage should not be sold to subscribers.
        if not self._cost_model.should_execute(gap_cents, self._min_profit_bps):
            FEED_ARB_SIGNALS_DROPPED_TOTAL.labels(reason="below_min_profit_bps").inc()
            return

        # Gross edge per spec §3.2: "edge_cents — gross edge at signal
        # emission, before fees and slippage." The CostModel.should_execute
        # gate above ensures only signals where gross > fees+slippage+min
        # get published; what subscribers see is the same raw gap number
        # they could compute from our publicly-disclosed Kalshi + Poly
        # price feeds. (Net-of-fees would require publishing our cost
        # model, which gets into proprietary territory and is a support
        # nightmare if our fees ever change.)
        edge_cents = abs(float(gap_cents))

        # Side derivation mirrors execution/arb_executor.py:195-196:
        #   gap_cents > 0 means Kalshi is more expensive than Polymarket,
        #   so we sell the Kalshi side and buy the Polymarket side.
        if gap_cents > 0:
            kalshi_side = "SELL"
            poly_side = "BUY"
        else:
            kalshi_side = "BUY"
            poly_side = "SELL"

        # ts / expires_at are stored as TEXT on SQLite (tests) and as
        # TIMESTAMPTZ on Postgres (prod). asyncpg refuses ISO strings on
        # TIMESTAMPTZ params (it wants datetime objects); aiosqlite accepts
        # either. Normalize to datetime internally and cast to ISO string
        # at INSERT time only for the SQLite path (detected by the absence
        # of the PostgresDB-specific `fetchone` helper).
        from datetime import datetime, timedelta, timezone

        observed_at = data.get("observed_at")
        if observed_at:
            try:
                ts_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            except Exception:
                ts_dt = datetime.now(timezone.utc)
        else:
            ts_dt = datetime.now(timezone.utc)
        expires_dt = ts_dt + timedelta(seconds=self._expiration_seconds)

        # Raw payload kept for forensics + future attribution queries.
        raw_signal_json = json.dumps(
            {
                **data,
                # Echo computed fields so the raw JSON is self-describing
                # without re-running the gate logic.
                "_computed": {
                    "edge_cents": edge_cents,
                    "kalshi_side": kalshi_side,
                    "poly_side": poly_side,
                    "min_profit_bps_threshold": self._min_profit_bps,
                },
            },
            default=_json_default,
        )

        # Postgres (asyncpg) wants datetime objects for TIMESTAMPTZ; SQLite
        # (aiosqlite) takes either but we pass ISO strings for clarity on
        # the TEXT columns. `fetchone` attribute is the same Postgres-vs-
        # SQLite discriminator used by storage/spreads.py.
        is_postgres = hasattr(self._db, "fetchone")
        ts_param: Any = ts_dt if is_postgres else ts_dt.isoformat()
        expires_param: Any = expires_dt if is_postgres else expires_dt.isoformat()

        await self._insert(
            signal_id=signal_id,
            ts=ts_param,
            kalshi_ticker=kalshi_ticker,
            kalshi_side=kalshi_side,
            poly_token_id=poly_ticker,
            poly_side=poly_side,
            edge_cents=edge_cents,
            max_size_usd=float(self._max_size_usd),
            expires_at=expires_param,
            raw_signal_json=raw_signal_json,
        )

    # ------------------------------------------------------------------
    # INSERT — dual-path SQLite + Postgres
    # ------------------------------------------------------------------

    async def _insert(
        self,
        *,
        signal_id: str,
        ts: Any,
        kalshi_ticker: str,
        kalshi_side: str,
        poly_token_id: str,
        poly_side: str,
        edge_cents: float,
        max_size_usd: float,
        expires_at: Any,
        raw_signal_json: str,
    ) -> None:
        """INSERT row into feed_arb_signals, deduplicating on signal_id.

        Signal_id is a ULID primary key — dedup via ON CONFLICT DO NOTHING.
        Uses INSERT OR IGNORE on SQLite (translated to ON CONFLICT DO NOTHING
        for Postgres by storage/postgres.py:_convert_insert_or_ignore).

        Swallow-with-log on error, so one bad write doesn't kill the
        subscription. log_event emits structured `error` events that the
        D4 alert rule can key off.
        """
        sql = (
            "INSERT OR IGNORE INTO feed_arb_signals "
            "(signal_id, ts, pair_kalshi_ticker, pair_kalshi_side, "
            " pair_poly_token_id, pair_poly_side, edge_cents, "
            " max_size_at_edge_usd, expires_at, raw_signal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            signal_id,
            ts,
            kalshi_ticker,
            kalshi_side,
            poly_token_id,
            poly_side,
            edge_cents,
            max_size_usd,
            expires_at,
            raw_signal_json,
        )
        try:
            await self._db.execute(sql, params)
            await self._db.commit()
            FEED_ARB_SIGNALS_PUBLISHED_TOTAL.inc()
            log_event(
                logger,
                logging.INFO,
                "feed.publish",
                "feed_arb_signals row written: %s" % signal_id,
                data={
                    "signal_id": signal_id,
                    "ts": ts,
                    "kalshi_ticker": kalshi_ticker,
                    "poly_token_id": poly_token_id,
                    "edge_cents": edge_cents,
                },
            )
        except Exception as exc:
            FEED_ARB_SIGNALS_DROPPED_TOTAL.labels(reason="store_error").inc()
            log_event(
                logger,
                logging.WARNING,
                "error",
                "FeedPublisher: INSERT failed for signal_id=%s: %s"
                % (signal_id, exc),
                data={
                    "component": "feed_publisher",
                    "signal_id": signal_id,
                    "exception_type": type(exc).__name__,
                },
            )


def _json_default(obj: Any) -> Any:
    """json.dumps default for Decimal and non-standard types in raw_signal."""
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
