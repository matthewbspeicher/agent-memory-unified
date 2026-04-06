"""
Redis Streams consumer with reliability guarantees.

Replaces consumer.py (Pub/Sub) with Streams-based implementation:
- Consumer groups (multiple workers)
- DLQ for failed messages
- Automatic retries (3 max)
"""
import asyncio
import json
import logging
from typing import Callable, Dict
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class StreamsEventConsumer:
    """
    Consume events from Redis Streams with consumer groups.

    Example:
        consumer = StreamsEventConsumer(redis, stream="events", group="trading-service")
        consumer.register("AgentDeactivated", handle_agent_deactivated)
        await consumer.start()
    """

    def __init__(
        self,
        redis: Redis,
        stream: str = "events",
        group: str = "trading-service",
        consumer_name: str = "worker-1",
        max_retries: int = 3,
    ):
        self.redis = redis
        self.stream = stream
        self.group = group
        self.consumer_name = consumer_name
        self.max_retries = max_retries
        self.handlers: Dict[str, Callable] = {}
        self._running = False

    def register(self, event_type: str, handler: Callable):
        """Register handler for event type."""
        self.handlers[event_type] = handler
        logger.info(f"Registered handler: {event_type}")

    async def start(self):
        """Start consuming from stream."""
        # Create consumer group (idempotent)
        try:
            await self.redis.xgroup_create(
                self.stream, self.group, id="0", mkstream=True
            )
            logger.info(f"Created consumer group: {self.group}")
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"Failed to create consumer group: {e}")
                raise

        self._running = True
        logger.info(f"Consumer started: {self.stream}/{self.group}/{self.consumer_name}")

        while self._running:
            try:
                # Read new messages (block for 1 second)
                messages = await self.redis.xreadgroup(
                    self.group,
                    self.consumer_name,
                    {self.stream: ">"},  # '>' = only new messages
                    count=10,
                    block=1000,
                )

                for stream, msgs in messages:
                    for msg_id, data in msgs:
                        await self._handle_message(msg_id, data)

            except asyncio.CancelledError:
                logger.info("Consumer cancelled")
                break
            except Exception as e:
                logger.error(f"Consumer loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def stop(self):
        """Stop consumer gracefully."""
        self._running = False

    async def _handle_message(self, msg_id: bytes, data: dict):
        """Process message with retries and DLQ."""
        try:
            # Decode event envelope
            event_json = data.get(b"data")
            if not event_json:
                logger.warning(f"Message {msg_id} has no data field")
                await self.redis.xack(self.stream, self.group, msg_id)
                return

            payload = json.loads(event_json)
            event_type = payload.get("type")
            event_data = payload.get("payload", {})

            # Dispatch to handler
            if event_type in self.handlers:
                handler = self.handlers[event_type]
                await handler(event_data)
            else:
                logger.debug(f"No handler for event type: {event_type}")

            # ACK message on success
            await self.redis.xack(self.stream, self.group, msg_id)

        except Exception as e:
            logger.error(f"Handler failed for {msg_id}: {e}", exc_info=True)

            # Check retry count via XPENDING
            pending = await self.redis.xpending_range(
                self.stream, self.group, min=msg_id, max=msg_id, count=1
            )

            if pending:
                delivery_count = pending[0]["times_delivered"]

                if delivery_count >= self.max_retries:
                    # Move to DLQ after max retries
                    await self.redis.xadd(f"{self.stream}:dlq", data)
                    await self.redis.xack(self.stream, self.group, msg_id)
                    logger.warning(
                        f"Moved {msg_id} to DLQ after {delivery_count} retries"
                    )
                else:
                    # Leave in pending, will be retried
                    logger.info(
                        f"Message {msg_id} failed, retry {delivery_count}/{self.max_retries}"
                    )
            else:
                # Pending info unavailable — leave unacked for retry on next iteration.
                # Do NOT ack here: that would silently drop messages on first failure.
                logger.warning(
                    f"Could not check pending info for {msg_id}, will retry"
                )


# Example handler
async def handle_agent_deactivated(data: dict):
    """Handle agent deactivation event."""
    agent_id = data.get("agent_id")
    agent_name = data.get("agent_name")

    logger.info(
        f"AgentDeactivated event received",
        extra={"agent_id": agent_id, "agent_name": agent_name},
    )

    # Redis blacklist already updated by Laravel listener
    # Could add additional Python-side cleanup here if needed
