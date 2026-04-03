import asyncio
import json
import logging
import uuid
from typing import Any, Optional
import redis.asyncio as redis
from data.events import EventBus

logger = logging.getLogger(__name__)

class RedisSignalBridge:
    """
    Bridges the local EventBus with a distributed Redis channel for
    cross-node signal and opportunity propagation.
    """
    def __init__(self, event_bus: EventBus, redis_url: str, node_id: Optional[str] = None):
        self._event_bus = event_bus
        self._redis_url = redis_url
        self._node_id = node_id or f"node-{uuid.uuid4().hex[:8]}"
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._bus_listener_task: Optional[asyncio.Task] = None
        self._redis_listener_task: Optional[asyncio.Task] = None
        self._channel = "sta_distributed_bus"
        self._running = False

    async def start(self):
        if self._running:
            return
        
        try:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
            # Test connection
            await self._redis.ping()
            
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(self._channel)
            
            self._running = True
            self._redis_listener_task = asyncio.create_task(self._listen_redis())
            self._bus_listener_task = asyncio.create_task(self._listen_event_bus())
            
            logger.info(f"RedisSignalBridge started on node {self._node_id} (channel: {self._channel})")
        except Exception as e:
            logger.error(f"Failed to start RedisSignalBridge: {e}")
            self._running = False

    async def stop(self):
        self._running = False
        if self._bus_listener_task:
            self._bus_listener_task.cancel()
        if self._redis_listener_task:
            self._redis_listener_task.cancel()
        if self._pubsub:
            await self._pubsub.unsubscribe(self._channel)
        if self._redis:
            await self._redis.close()
        logger.info("RedisSignalBridge stopped")

    async def _listen_event_bus(self):
        """Listen for local events and publish them to Redis."""
        try:
            async for event in self._event_bus.subscribe():
                if not self._running:
                    break
                    
                topic = event.get("topic")
                # We only bridge signals and opportunities
                if topic in ("agent_signal", "opportunity"):
                    data = event.get("data")
                    
                    # Skip if this event originated from Redis (prevent loops)
                    if isinstance(data, dict) and data.get("_remote_node") == self._node_id:
                        continue
                    
                    # Envelope for Redis
                    payload = {
                        "topic": topic,
                        "data": data,
                        "origin_node": self._node_id
                    }
                    
                    try:
                        await self._redis.publish(self._channel, json.dumps(payload))
                    except Exception as e:
                        logger.error(f"Failed to publish to Redis: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in EventBus listener: {e}")

    async def _listen_redis(self):
        """Listen for Redis messages and publish them to the local EventBus."""
        try:
            async for message in self._pubsub.listen():
                if not self._running:
                    break
                    
                if message["type"] == "message":
                    try:
                        payload = json.loads(message["data"])
                        origin = payload.get("origin_node")
                        
                        # Skip messages from self
                        if origin == self._node_id:
                            continue
                            
                        topic = payload.get("topic")
                        data = payload.get("data")
                        
                        if topic and data:
                            # Tag data so we don't re-broadcast it back to Redis
                            if isinstance(data, dict):
                                data["_remote_node"] = self._node_id
                                data["_origin_node"] = origin
                                
                            await self._event_bus.publish(topic, data)
                    except json.JSONDecodeError:
                        logger.warning(f"Received malformed JSON from Redis: {message['data']}")
                    except Exception as e:
                        logger.error(f"Failed to process Redis message: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self._running:
                logger.error(f"Error in Redis listener: {e}")
