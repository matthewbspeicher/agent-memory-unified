import asyncio
import logging
from typing import Any, AsyncGenerator, Callable, Awaitable

logger = logging.getLogger(__name__)


class BasePubSubBus:
    """Base class for async pub/sub buses."""

    def __init__(self, max_queue_size: int = 1000, max_subscribers: int = 10):
        self._queues: set[asyncio.Queue] = set()
        self._max_queue_size = max_queue_size
        self._max_subscribers = max_subscribers
        self._callbacks: list[Callable[[Any], Awaitable[None]]] = []

    async def publish(self, topic: str, data: Any) -> None:
        payload = {"topic": topic, "data": data}

        # Notify queue-based subscribers
        for q in list(self._queues):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

        # Notify callback-based subscribers
        for cb in self._callbacks:
            try:
                await cb(payload)
            except Exception as e:
                logger.error("Error in bus callback for topic %s: %s", topic, e)

    async def subscribe_gen(self) -> AsyncGenerator[dict[str, Any], None]:
        """Subscribe using an async generator."""
        if len(self._queues) >= self._max_subscribers:
            raise RuntimeError(f"Max subscribers ({self._max_subscribers}) reached")
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._queues.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._queues.discard(q)

    def subscribe_callback(self, callback: Callable[[Any], Awaitable[None]]) -> None:
        """Subscribe using a callback."""
        self._callbacks.append(callback)
