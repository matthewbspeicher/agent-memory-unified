# trading/events/consumer.py
"""
Event consumer for cross-service communication via Redis pub/sub.

Currently agent deactivation works via shared Redis blacklist,
but this consumer provides a framework for future event-driven features.
"""
import asyncio
import json
import logging
from typing import Callable, Dict
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class EventConsumer:
    """
    Subscribe to Redis pub/sub channels and dispatch to handlers.

    Example usage:
        consumer = EventConsumer(redis, channel="laravel-events")
        consumer.register("AgentDeactivated", handle_agent_deactivated)
        await consumer.start()
    """

    def __init__(self, redis: Redis, channel: str = "laravel-events"):
        self.redis = redis
        self.channel = channel
        self.handlers: Dict[str, Callable] = {}
        self._running = False
        self._pubsub = None

    def register(self, event_type: str, handler: Callable):
        """Register a handler for a specific event type."""
        self.handlers[event_type] = handler
        logger.info(f"Registered handler for event: {event_type}")

    async def start(self):
        """Start consuming events from Redis pub/sub."""
        self._running = True
        self._pubsub = self.redis.pubsub()
        await self._pubsub.subscribe(self.channel)

        logger.info(f"Event consumer started on channel: {self.channel}")

        try:
            async for message in self._pubsub.listen():
                if not self._running:
                    break

                if message["type"] == "message":
                    await self._handle_message(message["data"])
        finally:
            await self._pubsub.unsubscribe(self.channel)
            await self._pubsub.aclose()
            logger.info("Event consumer stopped")

    async def stop(self):
        """Stop the consumer gracefully."""
        self._running = False

    async def _handle_message(self, data: bytes):
        """Parse and dispatch event to registered handler."""
        try:
            payload = json.loads(data)
            event_type = payload.get("type")
            event_data = payload.get("data", {})

            if event_type in self.handlers:
                handler = self.handlers[event_type]
                await handler(event_data)
            else:
                logger.debug(f"No handler for event type: {event_type}")

        except json.JSONDecodeError:
            logger.warning(f"Failed to parse event data: {data}")
        except Exception as e:
            logger.error(f"Error handling event: {e}", exc_info=True)


# Example handler for AgentDeactivated event
async def handle_agent_deactivated(data: dict):
    """
    Handle agent deactivation event.

    Note: This is optional since the shared Redis blacklist
    already provides immediate revocation. This handler is here
    for demonstration and future extensibility.
    """
    agent_id = data.get("agent_id")
    agent_name = data.get("agent_name")

    logger.info(f"Received AgentDeactivated event", extra={
        "agent_id": agent_id,
        "agent_name": agent_name,
    })

    # Redis blacklist is already updated by Laravel listener
    # Could add additional Python-side cleanup here if needed
    # For example: invalidate caches, close WebSockets, etc.
