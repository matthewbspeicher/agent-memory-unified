"""Memory decay scheduler for MemClaw-style memory lifecycle.

Automatically marks memories as "outdated" based on their memory_type's
decay window. For example:
- task memories decay after 30 days
- episode memories decay after 45 days
- fact memories decay after 120 days
- preference memories decay after 365 days

Usage:
    scheduler = DecayScheduler(store, enabled=True)
    await scheduler.run_once()  # Run decay check once
    # Or schedule periodically:
    asyncio.create_task(scheduler.run_periodic(interval_seconds=3600))
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading.storage.memory import LocalMemoryStore

from trading.storage.memory import MEMORY_DECAY_DAYS, MemoryRecord

logger = logging.getLogger(__name__)


class DecayScheduler:
    """Scheduler that marks memories as outdated based on decay windows."""

    def __init__(
        self,
        store: LocalMemoryStore,
        enabled: bool = False,
        interval_seconds: int = 3600,  # Default: check every hour
    ):
        self._store = store
        self._enabled = enabled
        self._interval = interval_seconds
        self._running = False
        self._last_run: datetime | None = None
        self._decayed_count = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def last_run(self) -> datetime | None:
        return self._last_run

    @property
    def decayed_count(self) -> int:
        return self._decayed_count

    async def run_once(self) -> int:
        """Run decay check once and return number of memories decayed.

        Returns:
            Number of memories marked as outdated.
        """
        if not self._enabled:
            logger.debug("Decay scheduler is disabled")
            return 0

        if not self._store._db:
            raise RuntimeError("Store not connected")

        decayed = 0
        now = datetime.now(timezone.utc)

        # For each memory type with a decay window, find and mark outdated
        for memory_type, decay_days in MEMORY_DECAY_DAYS.items():
            try:
                # Find memories past decay threshold that aren't already outdated/deleted/archived
                sql = """
                    SELECT id FROM memories
                    WHERE memory_type = ?
                    AND status NOT IN ('outdated', 'deleted', 'archived')
                    AND datetime(created_at) < datetime('now', ?)
                """
                cursor = await self._store._db.execute(
                    sql, (memory_type, f"-{decay_days} days")
                )
                rows = await cursor.fetchall()

                if rows:
                    # Mark them as outdated
                    ids = [row["id"] for row in rows]
                    placeholders = ",".join("?" * len(ids))
                    update_sql = f"""
                        UPDATE memories
                        SET status = 'outdated', updated_at = ?
                        WHERE id IN ({placeholders})
                    """
                    await self._store._db.execute(update_sql, (now.isoformat(), *ids))
                    decayed += len(ids)
                    logger.info(
                        "Decayed %d %s memories (>%d days old)",
                        len(ids),
                        memory_type,
                        decay_days,
                    )

            except Exception as e:
                logger.error("Error decaying %s memories: %s", memory_type, e)

        if decayed > 0:
            await self._store._db.commit()

        self._last_run = now
        self._decayed_count += decayed
        logger.info("Decay run complete: %d memories decayed", decayed)
        return decayed

    async def run_periodic(self) -> None:
        """Run decay checks periodically until stopped."""
        if self._running:
            logger.warning("Decay scheduler already running")
            return

        self._running = True
        logger.info("Decay scheduler started (interval: %ds)", self._interval)

        try:
            while self._running:
                await self.run_once()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            logger.info("Decay scheduler cancelled")
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop the periodic scheduler."""
        self._running = False
        logger.info("Decay scheduler stop requested")

    def get_status(self) -> dict:
        """Get scheduler status for health checks."""
        return {
            "enabled": self._enabled,
            "running": self._running,
            "interval_seconds": self._interval,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "total_decayed": self._decayed_count,
        }


def create_decay_scheduler(
    store: LocalMemoryStore,
    enabled: bool = False,
    interval_seconds: int = 3600,
) -> DecayScheduler:
    """Factory function to create a DecayScheduler.

    Args:
        store: LocalMemoryStore instance
        enabled: Whether decay is enabled
        interval_seconds: Check interval in seconds
    """
    return DecayScheduler(
        store=store,
        enabled=enabled,
        interval_seconds=interval_seconds,
    )
