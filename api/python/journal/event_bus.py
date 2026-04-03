import asyncio
import logging
from typing import Callable, Dict, List, Any

logger = logging.getLogger("EventBus")


class EventBus:
    """
    Simple async pub/sub event bus for in-process event dispatch.
    Handlers are registered by event name and called in order when an event is emitted.
    """

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_name: str, handler: Callable):
        """Register a handler for an event type."""
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)
        logger.debug(f"Subscribed {handler.__qualname__} to '{event_name}'")

    def unsubscribe(self, event_name: str, handler: Callable):
        """Remove a handler for an event type."""
        if event_name in self._handlers:
            self._handlers[event_name] = [h for h in self._handlers[event_name] if h != handler]

    async def emit(self, event_name: str, event: Dict[str, Any]):
        """Emit an event to all registered handlers."""
        handlers = self._handlers.get(event_name, [])
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Handler {handler.__qualname__} failed on '{event_name}': {e}", exc_info=True)
