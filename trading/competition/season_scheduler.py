import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SeasonScheduler:
    def __init__(self, store, check_interval: int = 3600):
        self._store = store
        self._check_interval = check_interval
        self._task: asyncio.Task | None = None

    async def start(self):
        self._task = asyncio.create_task(self._run())
        logger.info("SeasonScheduler started")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("SeasonScheduler stopped")

    async def _run(self):
        while True:
            try:
                await self._check_season()
            except Exception:
                logger.exception("SeasonScheduler check failed")
            await asyncio.sleep(self._check_interval)

    async def _check_season(self):
        current, _ = await self._store.get_seasons()
        now = datetime.utcnow()

        if current is None:
            logger.info("No active season, creating new one")
            await self._store.create_next_season()
            return

        if current.ends_at < now:
            logger.info(f"Season {current.number} ended, applying soft reset")
            affected = await self._store.apply_soft_reset(current.id)
            logger.info(f"Soft reset applied to {affected} ratings")

            new_season = await self._store.create_next_season()
            logger.info(f"Created Season {new_season.number}")
