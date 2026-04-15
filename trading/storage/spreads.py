"""SpreadStore — persists arb spread observations for history and alerting."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class SpreadObservation:
    kalshi_ticker: str
    poly_ticker: str
    match_score: float
    kalshi_cents: int
    poly_cents: int
    gap_cents: int
    kalshi_volume: float = 0.0
    poly_volume: float = 0.0
    observed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SpreadStore:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def record(self, obs: SpreadObservation) -> int | None:
        """Insert a spread observation and return its id.

        Returns the inserted row's id on success, or None on error.
        Errors are logged and swallowed so observation recording never
        blocks the caller's main flow (matching, alerting, etc).
        """
        try:
            cursor = await self._db.execute(
                """INSERT INTO arb_spread_observations
                   (kalshi_ticker, poly_ticker, match_score, kalshi_cents, poly_cents,
                    gap_cents, kalshi_volume, poly_volume, observed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    obs.kalshi_ticker,
                    obs.poly_ticker,
                    obs.match_score,
                    obs.kalshi_cents,
                    obs.poly_cents,
                    obs.gap_cents,
                    obs.kalshi_volume,
                    obs.poly_volume,
                    obs.observed_at,
                ),
            )
            await self._db.commit()
            return cursor.lastrowid
        except Exception as exc:
            logger.warning("SpreadStore.record failed (non-fatal): %s", exc)
            return None

    async def get_history(
        self,
        kalshi_ticker: str,
        poly_ticker: str,
        hours: int = 24,
    ) -> list[SpreadObservation]:
        """Return observations for the pair within the last `hours` hours."""
        if hours <= 0:
            return []
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        try:
            cursor = await self._db.execute(
                """SELECT kalshi_ticker, poly_ticker, match_score, kalshi_cents, poly_cents,
                          gap_cents, kalshi_volume, poly_volume, observed_at
                   FROM arb_spread_observations
                   WHERE kalshi_ticker = ?
                     AND poly_ticker = ?
                     AND observed_at >= ?
                   ORDER BY observed_at ASC""",
                (kalshi_ticker, poly_ticker, cutoff),
            )
            rows = await cursor.fetchall()
            return [
                SpreadObservation(
                    kalshi_ticker=r[0],
                    poly_ticker=r[1],
                    match_score=r[2],
                    kalshi_cents=r[3],
                    poly_cents=r[4],
                    gap_cents=r[5],
                    kalshi_volume=r[6],
                    poly_volume=r[7],
                    observed_at=r[8],
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("SpreadStore.get_history failed: %s", exc)
            return []

    async def get_top_spreads(
        self, min_gap: int = 5, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return the most recent observation per pair with gap >= min_gap, ordered by gap desc."""
        try:
            cursor = await self._db.execute(
                """WITH latest AS (
                       SELECT kalshi_ticker, poly_ticker, MAX(observed_at) AS max_ts
                       FROM arb_spread_observations
                       GROUP BY kalshi_ticker, poly_ticker
                   )
                   SELECT o.id, o.kalshi_ticker, o.poly_ticker, o.match_score,
                          o.kalshi_cents, o.poly_cents, o.gap_cents, o.observed_at
                   FROM arb_spread_observations o
                   JOIN latest l
                     ON o.kalshi_ticker = l.kalshi_ticker
                    AND o.poly_ticker   = l.poly_ticker
                    AND o.observed_at  = l.max_ts
                   WHERE o.gap_cents >= ?
                     AND (o.is_claimed = 0 OR o.claimed_at < datetime('now', '-2 minutes'))
                   ORDER BY o.gap_cents DESC
                   LIMIT ?""",
                (min_gap, limit),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "kalshi_ticker": r[1],
                    "poly_ticker": r[2],
                    "match_score": r[3],
                    "kalshi_cents": r[4],
                    "poly_cents": r[5],
                    "gap_cents": r[6],
                    "observed_at": r[7],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("SpreadStore.get_top_spreads failed: %s", exc)
            return []

    async def get_observation(self, observation_id: int) -> dict[str, Any] | None:
        """Fetch a single spread observation by its ID."""
        try:
            cursor = await self._db.execute(
                """SELECT id, kalshi_ticker, poly_ticker, match_score, kalshi_cents,
                          poly_cents, gap_cents, kalshi_volume, poly_volume, observed_at
                   FROM arb_spread_observations
                   WHERE id = ?""",
                (observation_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "kalshi_ticker": row[1],
                "poly_ticker": row[2],
                "match_score": row[3],
                "kalshi_cents": row[4],
                "poly_cents": row[5],
                "gap_cents": row[6],
                "kalshi_volume": row[7],
                "poly_volume": row[8],
                "observed_at": row[9],
            }
        except Exception as exc:
            logger.warning("SpreadStore.get_observation failed: %s", exc)
            return None

    async def claim_spread(self, observation_id: int, claimant: str) -> bool:
        """
        Attempt to atomically claim a spread for arbitrage.
        Returns True if successful.
        """
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._db.execute(
            """UPDATE arb_spread_observations
               SET is_claimed = 1, claimed_at = ?, claimed_by = ?
               WHERE id = ? AND (is_claimed = 0 OR claimed_at < datetime('now', '-2 minutes'))""",
            (now, claimant, observation_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def release_spread(self, observation_id: int) -> None:
        """Release a claimed spread."""
        await self._db.execute(
            "UPDATE arb_spread_observations SET is_claimed = 0 WHERE id = ?",
            (observation_id,),
        )
        await self._db.commit()
