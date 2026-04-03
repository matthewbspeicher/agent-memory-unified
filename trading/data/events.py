import asyncio
from typing import Any, AsyncGenerator

MAX_QUEUE_SIZE = 1000
MAX_SUBSCRIBERS = 10


class EventBus:
    def __init__(self, max_queue_size: int = MAX_QUEUE_SIZE, max_subscribers: int = MAX_SUBSCRIBERS):
        self._queues: set[asyncio.Queue] = set()
        self._max_queue_size = max_queue_size
        self._max_subscribers = max_subscribers

    async def publish(self, topic: str, data: Any) -> None:
        payload = {"topic": topic, "data": data}
        for q in list(self._queues):
            if q.full():
                try:
                    q.get_nowait()  # drop oldest
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def subscribe(self) -> AsyncGenerator[dict[str, Any], None]:
        if len(self._queues) >= self._max_subscribers:
            raise RuntimeError(f"Max subscribers ({self._max_subscribers}) reached")
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._queues.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._queues.discard(q)
