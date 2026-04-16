"""Feed health monitor — fires alerts when the arb signal pipeline stalls.

Runs as a background task every 60s. Three alert types (D3/D4/D6 from the
plan's observability gate for G4 — public dashboard launch):

- **D3 — attribution stall:** `feed_arb_pnl_rollup` latest row older than
  `ATTRIBUTION_STALENESS_THRESHOLD_SECONDS`. Catches the case where the
  attribution job crashed or is looping without writing rollups. Only
  fires after the first rollup has ever been written — "no rollups yet"
  is the normal launch state (honest-tracker: no fake rollups) and is
  NOT an alert condition.

- **D4 — publisher zero-publish:** No new rows in `feed_arb_signals`
  within `PUBLISHER_ZERO_WINDOW_SECONDS`, despite scan activity upstream.
  Catches silent-failure regressions in the EventBus → publisher path
  (the class of bug we realized in A0). Only fires after we've ever
  seen signals — pre-first-signal state is not an alert.

- **D6 — subscriber churn:** Stub. Fires only when a paid-tier subscriber's
  poll rate drops to 0 within a paid window. Gated on Stripe being live
  (STA_STRIPE_ENABLED=true); inert in v1 since no paid subs exist yet.

D5 (public-endpoint SLO dashboard) is a docs deliverable, not a runtime
alert — see `docs/feeds/arb/slo-dashboard.md`.

## Cooldown

Each alert type has independent cooldown (`*_COOLDOWN_SECONDS`) so one
sustained incident produces one notification, not a flood. Cooldown
resets when the condition clears (rollup catches up / publisher writes
a new row).

## Notification channel

Uses the existing `CompositeNotifier.send_text(...)` that wraps
Slack/Discord/WhatsApp/LogNotifier per `trading/notifications/`. Failure
to deliver (network error, webhook config missing) is logged but does
NOT break the monitor loop — the monitor keeps ticking even if the
notification channel is down.

Spec:  docs/superpowers/specs/2026-04-15-arb-signal-feed-design.md §11
Plan:  ~/.claude/plans/temporal-spinning-flame.md D3/D4/D6
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from utils.logging import log_event

if TYPE_CHECKING:
    from notifications.composite import CompositeNotifier


logger = logging.getLogger(__name__)


# Defaults overridden via config (feed_* fields added in this change).
DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_ATTRIBUTION_STALENESS_SECONDS = 300  # 5 min per spec §11
DEFAULT_PUBLISHER_ZERO_WINDOW_SECONDS = 7200  # 2h sustained-zero per plan Risk #1
DEFAULT_ALERT_COOLDOWN_SECONDS = 1800  # 30 min between repeat alerts


@dataclass
class _AlertState:
    """Per-alert-type state tracking. Reset when the condition clears."""

    last_fired_at: datetime | None = None
    condition_started_at: datetime | None = None


class FeedHealthMonitor:
    """Background task that watches the feed pipeline and fires alerts.

    One instance per engine process. Instantiated in app.py lifespan.
    """

    def __init__(
        self,
        db: Any,
        notifier: CompositeNotifier | None,
        *,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        attribution_staleness_seconds: int = DEFAULT_ATTRIBUTION_STALENESS_SECONDS,
        publisher_zero_window_seconds: int = DEFAULT_PUBLISHER_ZERO_WINDOW_SECONDS,
        alert_cooldown_seconds: int = DEFAULT_ALERT_COOLDOWN_SECONDS,
        clock: Any | None = None,
    ) -> None:
        self._db = db
        self._notifier = notifier
        self._interval = int(interval_seconds)
        self._attr_stale = int(attribution_staleness_seconds)
        self._pub_zero_window = int(publisher_zero_window_seconds)
        self._cooldown = int(alert_cooldown_seconds)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._state: dict[str, _AlertState] = {
            "d3_attribution_stall": _AlertState(),
            "d4_publisher_zero": _AlertState(),
        }

    # ------------------------------------------------------------------
    # Loop entry
    # ------------------------------------------------------------------

    async def run(self) -> None:
        logger.info(
            "FeedHealthMonitor: starting (interval=%ds, attr_stale=%ds, pub_zero=%ds, cooldown=%ds)",
            self._interval,
            self._attr_stale,
            self._pub_zero_window,
            self._cooldown,
        )
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_event(
                    logger,
                    logging.ERROR,
                    "error",
                    "FeedHealthMonitor.tick crashed: %s" % exc,
                    data={
                        "component": "feed_health_monitor",
                        "exception_type": type(exc).__name__,
                    },
                    exc_info=True,
                )
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                raise

    async def tick(self) -> None:
        """Run one health-check cycle. All three checks are independent
        and any failure in one doesn't block the others."""
        now = self._clock()

        # Run checks in parallel-safe sequence. Swallow per-check errors
        # so a DB blip on one doesn't skip the others.
        for check_name, fn in (
            ("d3_attribution_stall", self._check_attribution_stall),
            ("d4_publisher_zero", self._check_publisher_zero),
        ):
            try:
                await fn(now)
            except Exception as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "error",
                    "FeedHealthMonitor %s check failed: %s" % (check_name, exc),
                    data={
                        "component": "feed_health_monitor",
                        "check": check_name,
                        "exception_type": type(exc).__name__,
                    },
                )

    # ------------------------------------------------------------------
    # D3 — attribution stall
    # ------------------------------------------------------------------

    async def _check_attribution_stall(self, now: datetime) -> None:
        latest_rollup = await self._latest_rollup_ts()
        state = self._state["d3_attribution_stall"]

        if latest_rollup is None:
            # No rollup has ever been written. Honest-tracker: this is
            # the normal pre-first-fill state, not an alert.
            state.condition_started_at = None
            return

        age_seconds = (now - latest_rollup).total_seconds()
        if age_seconds <= self._attr_stale:
            # Fresh — clear any in-flight condition.
            if state.condition_started_at is not None:
                log_event(
                    logger,
                    logging.INFO,
                    "feed.health.recovered",
                    "D3 attribution staleness cleared (age=%ds)" % int(age_seconds),
                    data={"alert": "d3_attribution_stall", "age_seconds": int(age_seconds)},
                )
            state.condition_started_at = None
            return

        # Stale. Record start + maybe fire.
        if state.condition_started_at is None:
            state.condition_started_at = now

        if not self._cooldown_ok(state, now):
            return

        msg = (
            "🔴 D3 feed_arb_pnl_rollup stale: latest rollup is %d seconds old "
            "(threshold %ds). Latest rollup_ts=%s, now=%s. "
            "Attribution job may be crashed or stuck — check container logs "
            "for `FeedArbPnLAttribution.tick crashed`."
        ) % (int(age_seconds), self._attr_stale, latest_rollup.isoformat(), now.isoformat())
        await self._send_alert("d3_attribution_stall", msg, now)

    async def _latest_rollup_ts(self) -> datetime | None:
        sql = "SELECT MAX(rollup_ts) AS ts FROM feed_arb_pnl_rollup"
        try:
            if hasattr(self._db, "fetchone"):
                row = await self._db.fetchone(sql, ())
            else:
                cursor = await self._db.execute(sql)
                row = await cursor.fetchone()
        except Exception:
            return None
        if not row or row["ts"] is None:
            return None
        return _to_aware_utc(row["ts"])

    # ------------------------------------------------------------------
    # D4 — publisher zero-publish during a sustained window
    # ------------------------------------------------------------------

    async def _check_publisher_zero(self, now: datetime) -> None:
        total = await self._total_signals_count()
        state = self._state["d4_publisher_zero"]

        if total == 0:
            # Pre-first-signal — normal launch state, not an alert.
            state.condition_started_at = None
            return

        recent_count = await self._signals_since_count(
            now, seconds=self._pub_zero_window
        )
        if recent_count > 0:
            if state.condition_started_at is not None:
                log_event(
                    logger,
                    logging.INFO,
                    "feed.health.recovered",
                    "D4 publisher zero-publish cleared (recent=%d)" % recent_count,
                    data={"alert": "d4_publisher_zero", "recent": recent_count},
                )
            state.condition_started_at = None
            return

        # Zero publishes in the sustained window. Fire if past cooldown.
        if state.condition_started_at is None:
            state.condition_started_at = now

        if not self._cooldown_ok(state, now):
            return

        msg = (
            "🟠 D4 feed_arb_signals zero publishes in last %d seconds (%d hours). "
            "Total signals ever = %d, so publisher *has* worked before. "
            "Possible causes: arb.spread EventBus not firing (check scan logs), "
            "publisher subscription dropped, or adapters not producing candidates. "
            "Prediction markets trade 24/7, so this is not a market-hours gap."
        ) % (self._pub_zero_window, self._pub_zero_window // 3600, total)
        await self._send_alert("d4_publisher_zero", msg, now)

    async def _total_signals_count(self) -> int:
        sql = "SELECT COUNT(*) AS n FROM feed_arb_signals"
        try:
            if hasattr(self._db, "fetchone"):
                row = await self._db.fetchone(sql, ())
            else:
                cursor = await self._db.execute(sql)
                row = await cursor.fetchone()
        except Exception:
            return 0
        return int(row["n"] or 0) if row else 0

    async def _signals_since_count(self, now: datetime, *, seconds: int) -> int:
        """COUNT(*) from feed_arb_signals WHERE ts > (now - seconds)."""
        is_postgres = hasattr(self._db, "fetchone")
        threshold = datetime.fromtimestamp(
            now.timestamp() - seconds, tz=timezone.utc
        )
        threshold_param: Any = threshold if is_postgres else threshold.isoformat()
        sql = "SELECT COUNT(*) AS n FROM feed_arb_signals WHERE ts > ?"
        try:
            if is_postgres:
                row = await self._db.fetchone(sql, (threshold_param,))
            else:
                cursor = await self._db.execute(sql, (threshold_param,))
                row = await cursor.fetchone()
        except Exception:
            return 0
        return int(row["n"] or 0) if row else 0

    # ------------------------------------------------------------------
    # Alert dispatch
    # ------------------------------------------------------------------

    def _cooldown_ok(self, state: _AlertState, now: datetime) -> bool:
        """True if the alert is past its cooldown window."""
        if state.last_fired_at is None:
            return True
        elapsed = (now - state.last_fired_at).total_seconds()
        return elapsed >= self._cooldown

    async def _send_alert(self, alert_id: str, body: str, now: datetime) -> None:
        """Dispatch via the notifier; log the event regardless of whether
        the notifier is wired. Structured log lets D5 dashboard show
        alert-firing history even when no outbound webhooks exist."""
        state = self._state[alert_id]
        state.last_fired_at = now

        log_event(
            logger,
            logging.WARNING,
            "feed.health.alert",
            "FeedHealthMonitor alert fired: %s" % alert_id,
            data={
                "alert": alert_id,
                "body": body,
                "fired_at": now.isoformat(),
                "condition_started_at": (
                    state.condition_started_at.isoformat()
                    if state.condition_started_at
                    else None
                ),
            },
        )

        if self._notifier is None:
            return

        try:
            await self._notifier.send_text(body)
        except Exception as exc:
            # Notifier failure must not break the monitor loop — the
            # structured log above still captures the alert for the
            # audit trail.
            log_event(
                logger,
                logging.WARNING,
                "error",
                "FeedHealthMonitor notifier.send_text failed: %s" % exc,
                data={
                    "component": "feed_health_monitor",
                    "alert": alert_id,
                    "exception_type": type(exc).__name__,
                },
            )


def _to_aware_utc(v: Any) -> datetime | None:
    """Coerce a DB ts value (datetime or ISO string) to tz-aware UTC."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None
