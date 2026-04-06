from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from agents.models import AgentSignal

if TYPE_CHECKING:
    from data.signal_bus import SignalBus

logger = logging.getLogger(__name__)


class SignalAdapter(ABC):
    @abstractmethod
    async def poll(self) -> list[AgentSignal]: ...

    @abstractmethod
    def source_name(self) -> str: ...


class SignalAdapterRunner:
    def __init__(self, adapters: list[SignalAdapter], signal_bus: SignalBus) -> None:
        self._adapters = {a.source_name(): a for a in adapters}
        self._signal_bus = signal_bus
        self._tasks: dict[str, asyncio.Task] = {}

    async def poll_once(self, adapter_name: str) -> None:
        adapter = self._adapters.get(adapter_name)
        if not adapter:
            logger.warning("Unknown adapter: %s", adapter_name)
            return
        try:
            signals = await adapter.poll()
            for sig in signals:
                await self._signal_bus.publish(sig)
            if signals:
                logger.info(
                    "Adapter '%s' produced %d signals", adapter_name, len(signals)
                )
        except Exception as e:
            logger.error("Adapter '%s' poll failed: %s", adapter_name, e)

    async def _poll_loop(self, adapter_name: str, interval: int) -> None:
        while True:
            await self.poll_once(adapter_name)
            await asyncio.sleep(interval)

    def start(self, intervals: dict[str, int] | None = None) -> None:
        intervals = intervals or {}
        for name in self._adapters:
            interval = intervals.get(name, 300)
            self._tasks[name] = asyncio.create_task(self._poll_loop(name, interval))
            logger.info("Started adapter '%s' with interval=%ds", name, interval)

    async def stop(self) -> None:
        for name, task in self._tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped adapter '%s'", name)
        self._tasks.clear()
