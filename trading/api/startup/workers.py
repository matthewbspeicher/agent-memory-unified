"""Background workers orchestration for FastAPI lifespan.

Manages lifecycle of long-running asyncio tasks:
- DailyTradeCompiler
- FidelityFileWatcher
- BittensorScheduler
- SignalBus subscriptions
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from learning.trade_compiler import DailyTradeCompiler


class BackgroundWorkers:
    """Manages background asyncio tasks across the application lifespan."""

    def __init__(self, app: FastAPI, logger: logging.Logger | None = None):
        self.app = app
        self.logger = logger or logging.getLogger(__name__)
        self.tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        """Start all registered background workers."""
        self._running = True
        self.logger.info("Starting background workers")

        if hasattr(self.app.state, "trade_compiler"):
            tc: DailyTradeCompiler = self.app.state.trade_compiler
            task = asyncio.create_task(tc.start_loop(), name="daily_trade_compiler")
            self.tasks.append(task)
            self.logger.info("Registered DailyTradeCompiler task")

    async def stop(self) -> None:
        """Stop all background workers gracefully."""
        self._running = False
        self.logger.info("Stopping background workers, %d tasks", len(self.tasks))

        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
                except asyncio.TimeoutError:
                    self.logger.warning(
                        "Task %s did not cancel in time", task.get_name()
                    )
                except asyncio.CancelledError:
                    pass

        self.tasks.clear()
        self.logger.info("All background workers stopped")

    @property
    def running(self) -> bool:
        return self._running


def create_workers(
    app: FastAPI, logger: logging.Logger | None = None
) -> BackgroundWorkers:
    """Factory to create BackgroundWorkers instance."""
    return BackgroundWorkers(app, logger)
