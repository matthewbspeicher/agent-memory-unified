"""Tracked background task manager for clean startup/shutdown."""

from __future__ import annotations

import asyncio
import logging
from typing import Coroutine

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """Registry for background asyncio tasks with exception logging and clean shutdown."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    @property
    def active_tasks(self) -> dict[str, asyncio.Task]:
        return {k: v for k, v in self._tasks.items() if not v.done()}

    def create_task(self, coro: Coroutine, *, name: str) -> asyncio.Task:
        if name in self._tasks and not self._tasks[name].done():
            raise ValueError(f"Task '{name}' is already registered and active")
        task = asyncio.create_task(coro, name=name)
        self._tasks[name] = task
        task.add_done_callback(lambda t: self._on_task_done(name, t))
        return task

    def _on_task_done(self, name: str, task: asyncio.Task) -> None:
        self._tasks.pop(name, None)
        if task.cancelled():
            logger.info("Background task '%s' cancelled", name)
            return
        exc = task.exception()
        if exc:
            logger.error(
                "Background task '%s' failed: %s: %s",
                name,
                type(exc).__name__,
                exc,
            )

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
