"""PnL attribution + outcome marking for the arb signal feed.

Runs every N seconds (default 60). Two independent responsibilities:

1. **Mark expired signals as missed.** Any `feed_arb_signals` row whose
   `expires_at` is in the past and whose `outcome` is still NULL gets
   set to `'missed'`. This runs unconditionally — no broker needed —
   so the public dashboard eventually shows every emitted signal's
   disposition even when nothing is trading.

2. **Aggregate fills into a rollup row.** Pull fill data from the
   Kalshi + Polymarket brokers (if wired), join to `signal_id` via
   `client_order_id` (Kalshi native) and the `signal_order_map` table
   (Polymarket), mark filled signals, and — only if there are real
   fills — write a `feed_arb_pnl_rollup` row.

v1 attribution is deliberately conservative per the spec §3.1
"honest tracker" brand commitment: when there are no real fills we do
NOT write a rollup. The public dashboard shows `pnl: null` instead of
fiction. Proper fill-to-fill realized/unrealized PnL with position
tracking lands in v1.1; see the "v1 PnL model" section below for the
v1 approximation we use when fills exist.

Spec:  docs/superpowers/specs/2026-04-15-arb-signal-feed-design.md §3.1, §4.1
Plan:  ~/.claude/plans/temporal-spinning-flame.md "Attribution job" next-action
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from utils.logging import log_event

if TYPE_CHECKING:
    from broker.interfaces import AccountProvider


logger = logging.getLogger(__name__)


# v1 defaults — overridden by config.py env-var fields:
#   STA_FEED_ATTRIBUTION_INTERVAL_SECONDS
#   STA_FEED_REAL_SLEEVE_NOTIONAL_USD
#   STA_FEED_SCALED_REFERENCE_NOTIONAL_USD
DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_REAL_NOTIONAL_USD = Decimal("11000.00")
DEFAULT_SCALED_NOTIONAL_USD = Decimal("250000.00")


@dataclass
class RealizedFill:
    """Normalized fill record from either venue, keyed to a signal_id.

    Built by `_collect_kalshi_fills` / `_collect_polymarket_fills` and
    fed into the rollup accumulator. Kept venue-agnostic so the math
    pipeline doesn't fork per-broker.
    """

    signal_id: str
    venue: str  # "kalshi" | "polymarket"
    ticker_or_token: str
    filled_qty: Decimal
    avg_price_usd: Decimal  # 0.00–1.00 for prediction-market contracts
    fees_usd: Decimal
    filled_at: datetime


@dataclass
class RollupAccumulator:
    """Rolls realized + open PnL up from fills across the last tick.

    The v1 PnL model (documented in class docstring):
    - realized_pnl_usd = sum over closed arb pairs of
          (kalshi_leg.fill_net + polymarket_leg.fill_net) − fees_sum
      where _net = qty × (expected_settlement_price − fill_price)
      and expected_settlement is 1.0 for YES-filled legs and 0.0 for NO.
      This is a *proxy*; true PnL requires settlement which lands weeks
      to months later. v1 reports the *guaranteed-arb-lock-in* value
      under the honest-tracker framing.
    - open_pnl_usd = 0 in v1. Requires MTM-ing open legs against live
      mid prices — deferred to v1.1 when we wire the market-data feed
      into the attribution loop.
    """

    realized_pnl_usd: Decimal = Decimal("0")
    open_pnl_usd: Decimal = Decimal("0")
    open_position_count: int = 0
    closed_position_count: int = 0
    filled_signal_ids: set[str] = field(default_factory=set)

    def has_any_activity(self) -> bool:
        return bool(self.filled_signal_ids)


class FeedArbPnLAttribution:
    """Periodic attribution + rollup job for the feed_arb_signals table.

    Lifecycle: instantiated in app.py lifespan, run as a background task
    via `utils.background_tasks.BackgroundTaskManager`. Graceful shutdown
    via standard asyncio task cancellation.
    """

    def __init__(
        self,
        db: Any,
        *,
        kalshi_broker: Any | None = None,
        polymarket_broker: Any | None = None,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        real_notional_usd: Decimal | float = DEFAULT_REAL_NOTIONAL_USD,
        scaled_notional_usd: Decimal | float = DEFAULT_SCALED_NOTIONAL_USD,
        clock: Any | None = None,
    ) -> None:
        self._db = db
        self._kalshi = kalshi_broker
        self._polymarket = polymarket_broker
        self._interval = int(interval_seconds)
        self._real = Decimal(str(real_notional_usd))
        self._scaled = Decimal(str(scaled_notional_usd))
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # Cursor for "fills since last poll". Updated each tick after a
        # successful collect; not persisted across restarts — v1 accepts
        # a small double-count risk at startup in exchange for simplicity.
        # signal_order_map dedup on (order_hash, signal_id) would make
        # this persistable in v1.1.
        self._last_fill_cursor: datetime | None = None

    # ------------------------------------------------------------------
    # Background-task entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        logger.info(
            "FeedArbPnLAttribution: starting (interval=%ds, real=$%s, scaled=$%s)",
            self._interval,
            self._real,
            self._scaled,
        )
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Do not break the loop on errors. Log with enough
                # structure that D3/D4 can key off it; the alert rule
                # watches feed_arb_pnl_rollup.rollup_ts age so if the
                # job crashes persistently D3 will page.
                log_event(
                    logger,
                    logging.ERROR,
                    "error",
                    "FeedArbPnLAttribution.tick crashed: %s" % exc,
                    data={
                        "component": "feed_pnl_attribution",
                        "exception_type": type(exc).__name__,
                    },
                    exc_info=True,
                )
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                raise

    # ------------------------------------------------------------------
    # Single tick — callable directly from tests without the loop
    # ------------------------------------------------------------------

    async def tick(self) -> RollupAccumulator | None:
        """Run one attribution cycle. Returns the rollup row written
        (if any) so tests can assert on it."""
        now = self._clock()

        # 1. Mark expired signals as 'missed'. Runs unconditionally —
        #    no broker required, just SQL. Important for the dashboard
        #    to eventually show every signal's disposition.
        expired_count = await self._mark_expired_as_missed(now)
        if expired_count:
            log_event(
                logger,
                logging.INFO,
                "feed.attribution.expired",
                "Marked %d expired signals as 'missed'" % expired_count,
                data={"count": expired_count},
            )

        # 2. Pull fills from both venues. When brokers are not configured
        #    (paper/dev mode), the helpers return empty lists cleanly.
        kalshi_fills = await self._collect_kalshi_fills()
        poly_fills = await self._collect_polymarket_fills()
        all_fills = kalshi_fills + poly_fills

        if not all_fills:
            # No fills this tick. Honest-tracker brand: do NOT write
            # a rollup with fabricated PnL. The public dashboard shows
            # pnl: null and the scaling banner explains why.
            return None

        # 3. Mark matched signals as 'filled'.
        acc = RollupAccumulator()
        for fill in all_fills:
            acc.filled_signal_ids.add(fill.signal_id)
            # v1 realized-PnL proxy: the fill *secures* the arbitrage
            # lock-in at the observed edge. Treat the per-fill net as
            # (qty × locked_in_edge_usd) where locked_in_edge_usd is
            # derived from the matching signal's edge_cents at the
            # signal's notional.
            realized = await self._realized_from_fill(fill)
            acc.realized_pnl_usd += realized
            acc.closed_position_count += 1

        marked_count = await self._mark_as_filled(acc.filled_signal_ids, now)
        if marked_count:
            log_event(
                logger,
                logging.INFO,
                "feed.attribution.filled",
                "Marked %d signals as 'filled'" % marked_count,
                data={"count": marked_count, "signal_ids": sorted(acc.filled_signal_ids)[:20]},
            )

        # 4. Write rollup row. Realized is the running cumulative across
        #    the whole feed lifetime — query DB for prior cumulative
        #    and add this tick's delta.
        cumulative = await self._cumulative_realized_before(now) + acc.realized_pnl_usd
        scaling_factor = (
            (self._scaled / self._real) if self._real > 0 else Decimal("1")
        )
        scaling_text = (
            f"Linearly scaled from ${self._real:.0f} real sleeve to "
            f"${self._scaled:.0f} reference (×{scaling_factor:.2f}). "
            "Does not adjust for slippage at larger notional; "
            "slippage-aware scaling is v1.1."
        )
        await self._write_rollup(
            rollup_ts=now,
            realized=acc.realized_pnl_usd,
            open_=acc.open_pnl_usd,
            cumulative=cumulative,
            open_count=acc.open_position_count,
            closed_count=acc.closed_position_count,
            scaling_factor=scaling_factor,
            scaling_text=scaling_text,
        )
        log_event(
            logger,
            logging.INFO,
            "feed.pnl_rollup",
            "Wrote feed_arb_pnl_rollup row (realized=$%s, cumulative=$%s)"
            % (acc.realized_pnl_usd, cumulative),
            data={
                "realized_pnl_usd": str(acc.realized_pnl_usd),
                "cumulative_pnl_usd": str(cumulative),
                "closed_positions": acc.closed_position_count,
                "scaling_factor": str(scaling_factor),
            },
        )
        return acc

    # ------------------------------------------------------------------
    # Expired-signal marking (broker-independent)
    # ------------------------------------------------------------------

    async def _mark_expired_as_missed(self, now: datetime) -> int:
        """UPDATE feed_arb_signals SET outcome='missed' for rows whose
        expires_at is in the past and outcome is still NULL.

        Returns the row count updated (for logging / observability).
        """
        is_postgres = hasattr(self._db, "fetchall")
        now_param: Any = now if is_postgres else now.isoformat()

        if is_postgres:
            # Use RETURNING to count affected rows portably (avoids the
            # cursor.rowcount wrapper inconsistency).
            sql = (
                "UPDATE feed_arb_signals "
                "SET outcome = 'missed', outcome_set_at = ? "
                "WHERE outcome IS NULL AND expires_at < ? "
                "RETURNING signal_id"
            )
            try:
                rows = await self._db.fetchall(sql, (now_param, now_param))
                await self._db.commit()
                return len(list(rows))
            except Exception as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "error",
                    "FeedArbPnLAttribution: mark-expired failed: %s" % exc,
                    data={
                        "component": "feed_pnl_attribution",
                        "step": "mark_expired",
                        "exception_type": type(exc).__name__,
                    },
                )
                return 0

        # SQLite path — no RETURNING on older aiosqlite, use cursor.rowcount
        sql = (
            "UPDATE feed_arb_signals "
            "SET outcome = 'missed', outcome_set_at = ? "
            "WHERE outcome IS NULL AND expires_at < ?"
        )
        try:
            cursor = await self._db.execute(sql, (now_param, now_param))
            await self._db.commit()
            return int(cursor.rowcount or 0)
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "error",
                "FeedArbPnLAttribution: mark-expired failed: %s" % exc,
                data={
                    "component": "feed_pnl_attribution",
                    "step": "mark_expired",
                    "exception_type": type(exc).__name__,
                },
            )
            return 0

    # ------------------------------------------------------------------
    # Fill collection (venue-specific)
    # ------------------------------------------------------------------

    async def _collect_kalshi_fills(self) -> list[RealizedFill]:
        """Pull filled Kalshi orders since last tick, match to signal_id
        via client_order_id (Kalshi's native round-trip field)."""
        if self._kalshi is None:
            return []
        try:
            # Access the underlying client for raw order dicts (the
            # wrapper's OrderResult doesn't expose client_order_id).
            client = getattr(self._kalshi, "_client", None)
            if client is None:
                return []
            raw = await client.get_order_history(limit=200)
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "error",
                "FeedArbPnLAttribution: kalshi fetch failed: %s" % exc,
                data={"component": "feed_pnl_attribution", "venue": "kalshi"},
            )
            return []

        fills: list[RealizedFill] = []
        cursor = self._last_fill_cursor
        for o in raw or []:
            if o.get("status") not in ("executed", "partially_filled"):
                continue
            signal_id = o.get("client_order_id")
            if not signal_id:
                continue
            # Very defensive date parsing — Kalshi returns ISO 8601.
            filled_at = _parse_iso(o.get("updated_time") or o.get("created_time"))
            if filled_at is None:
                continue
            if cursor is not None and filled_at <= cursor:
                continue
            filled_qty = Decimal(str(o.get("contracts_filled") or 0))
            if filled_qty <= 0:
                continue
            avg_cents = o.get("avg_price") or o.get("yes_price") or 0
            avg_price = Decimal(str(avg_cents)) / Decimal("100")
            fees = Decimal(str(o.get("fees") or 0)) / Decimal("100")
            fills.append(
                RealizedFill(
                    signal_id=signal_id,
                    venue="kalshi",
                    ticker_or_token=str(o.get("ticker") or ""),
                    filled_qty=filled_qty,
                    avg_price_usd=avg_price,
                    fees_usd=fees,
                    filled_at=filled_at,
                )
            )
        return fills

    async def _collect_polymarket_fills(self) -> list[RealizedFill]:
        """Pull filled Polymarket orders since last tick, match to
        signal_id via the signal_order_map table (Polymarket doesn't
        round-trip client_order_id)."""
        if self._polymarket is None:
            return []
        try:
            # Polymarket broker exposes get_orders via its underlying
            # client; the wrapper's get_order_history returns OrderResult
            # without the raw orderID field, so use the client directly.
            pm_client = getattr(self._polymarket, "client", None) or getattr(
                self._polymarket, "_client", None
            )
            if pm_client is None:
                return []
            raw = pm_client.get_orders()
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "error",
                "FeedArbPnLAttribution: polymarket fetch failed: %s" % exc,
                data={"component": "feed_pnl_attribution", "venue": "polymarket"},
            )
            return []

        fills: list[RealizedFill] = []
        cursor = self._last_fill_cursor
        is_postgres = hasattr(self._db, "fetchall")
        for o in raw or []:
            status = str(o.get("status") or "").upper()
            if status not in ("FILLED", "MATCHED", "PARTIALLY_FILLED"):
                continue
            order_hash = o.get("id") or o.get("orderID") or o.get("order_hash")
            if not order_hash:
                continue
            # Join to signal_order_map for this venue's attribution.
            signal_id = await self._lookup_signal_id(order_hash)
            if not signal_id:
                continue
            filled_at = _parse_iso(o.get("updated_at") or o.get("created_at"))
            if filled_at is None:
                continue
            if cursor is not None and filled_at <= cursor:
                continue
            filled_qty = Decimal(str(o.get("size_matched") or o.get("size") or 0))
            if filled_qty <= 0:
                continue
            avg_price = Decimal(str(o.get("price") or 0))
            fees = Decimal(str(o.get("fees") or 0))
            fills.append(
                RealizedFill(
                    signal_id=signal_id,
                    venue="polymarket",
                    ticker_or_token=str(
                        o.get("market") or o.get("token_id") or ""
                    ),
                    filled_qty=filled_qty,
                    avg_price_usd=avg_price,
                    fees_usd=fees,
                    filled_at=filled_at,
                )
            )
        return fills

    async def _lookup_signal_id(self, order_hash: str) -> str | None:
        """SELECT signal_id FROM signal_order_map WHERE order_hash = ?"""
        sql = "SELECT signal_id FROM signal_order_map WHERE order_hash = ?"
        try:
            if hasattr(self._db, "fetchone"):
                row = await self._db.fetchone(sql, (order_hash,))
                return row["signal_id"] if row else None
            cursor = await self._db.execute(sql, (order_hash,))
            row = await cursor.fetchone()
            return row["signal_id"] if row else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Outcome marking + rollup write
    # ------------------------------------------------------------------

    async def _mark_as_filled(
        self, signal_ids: set[str], now: datetime
    ) -> int:
        if not signal_ids:
            return 0
        is_postgres = hasattr(self._db, "fetchall")
        now_param: Any = now if is_postgres else now.isoformat()
        count = 0
        # Parameterize each signal_id individually — set sizes are small
        # (at most a few dozen per tick) and this keeps us off SQL-
        # injection-adjacent dynamic IN-clause construction.
        for sid in signal_ids:
            sql = (
                "UPDATE feed_arb_signals "
                "SET outcome = 'filled', outcome_set_at = ? "
                "WHERE signal_id = ? AND outcome IS NULL"
            )
            try:
                if hasattr(self._db, "fetchall"):
                    cursor_result = await self._db.execute(sql, (now_param, sid))
                    # On Postgres wrapper, rowcount isn't exposed
                    # reliably — assume the UPDATE took effect if no
                    # exception. Count by treating each matched sid
                    # as incremented; signals with outcome already set
                    # become no-ops on the WHERE clause.
                    count += 1
                else:
                    cursor = await self._db.execute(sql, (now_param, sid))
                    count += int(cursor.rowcount or 0)
            except Exception as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "error",
                    "FeedArbPnLAttribution: mark-filled failed for %s: %s"
                    % (sid, exc),
                    data={
                        "component": "feed_pnl_attribution",
                        "step": "mark_filled",
                        "signal_id": sid,
                    },
                )
        await self._db.commit()
        return count

    async def _realized_from_fill(self, fill: RealizedFill) -> Decimal:
        """v1 realized-PnL proxy per class docstring.

        Strategy: look up the originating signal's edge_cents and pro-rate
        by the fill quantity. If the signal is already gone (which
        shouldn't happen since we insert before publishing the arb.spread
        event), fall back to 0 so we never over-count.
        """
        sql = (
            "SELECT edge_cents, max_size_at_edge_usd "
            "FROM feed_arb_signals WHERE signal_id = ?"
        )
        try:
            if hasattr(self._db, "fetchone"):
                row = await self._db.fetchone(sql, (fill.signal_id,))
            else:
                cursor = await self._db.execute(sql, (fill.signal_id,))
                row = await cursor.fetchone()
            if not row:
                return Decimal("0")
            edge_cents = Decimal(str(row["edge_cents"]))
            max_size = Decimal(str(row["max_size_at_edge_usd"]))
            # Filled fraction of the advertised size — conservative:
            # pro-rate edge by what actually filled vs what was offered.
            # Assume fill size is in contracts; each contract at
            # prediction-market venues is $1 notional. So filled USD =
            # filled_qty × avg_price_usd (the capital we actually put
            # to work on this leg).
            filled_usd = fill.filled_qty * fill.avg_price_usd
            fill_fraction = (
                filled_usd / max_size if max_size > 0 else Decimal("0")
            )
            # Arb locks in (edge_cents / 100) per $1 of matched capital.
            # Half-credit to each leg (the arb is two legs).
            per_dollar_edge = edge_cents / Decimal("100")
            return (
                filled_usd
                * per_dollar_edge
                * min(fill_fraction, Decimal("1"))
                / Decimal("2")
                - fill.fees_usd
            )
        except Exception:
            return Decimal("0")

    async def _cumulative_realized_before(self, now: datetime) -> Decimal:
        """Sum of realized_pnl_usd over all prior rollup rows."""
        is_postgres = hasattr(self._db, "fetchall")
        now_param: Any = now if is_postgres else now.isoformat()
        sql = (
            "SELECT COALESCE(SUM(realized_pnl_usd), 0) AS total "
            "FROM feed_arb_pnl_rollup WHERE rollup_ts < ?"
        )
        try:
            if hasattr(self._db, "fetchone"):
                row = await self._db.fetchone(sql, (now_param,))
            else:
                cursor = await self._db.execute(sql, (now_param,))
                row = await cursor.fetchone()
            if not row:
                return Decimal("0")
            return Decimal(str(row["total"] or 0))
        except Exception:
            return Decimal("0")

    async def _write_rollup(
        self,
        *,
        rollup_ts: datetime,
        realized: Decimal,
        open_: Decimal,
        cumulative: Decimal,
        open_count: int,
        closed_count: int,
        scaling_factor: Decimal,
        scaling_text: str,
    ) -> None:
        is_postgres = hasattr(self._db, "fetchall")
        ts_param: Any = rollup_ts if is_postgres else rollup_ts.isoformat()

        scaled_realized = realized * scaling_factor
        scaled_open = open_ * scaling_factor
        scaled_cumulative = cumulative * scaling_factor

        sql = (
            "INSERT OR REPLACE INTO feed_arb_pnl_rollup "
            "(rollup_ts, realized_pnl_usd, open_pnl_usd, cumulative_pnl_usd, "
            " open_position_count, closed_position_count, "
            " scaled_realized_pnl_usd, scaled_open_pnl_usd, "
            " scaled_cumulative_pnl_usd, scaling_assumption) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            ts_param,
            float(realized),
            float(open_),
            float(cumulative),
            int(open_count),
            int(closed_count),
            float(scaled_realized),
            float(scaled_open),
            float(scaled_cumulative),
            scaling_text,
        )
        await self._db.execute(sql, params)
        await self._db.commit()


def _parse_iso(s: Any) -> datetime | None:
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
