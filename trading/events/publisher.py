import json
import redis.asyncio as redis
from typing import Dict, Any, Optional

class EventPublisher:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None

    async def connect(self):
        self.client = redis.Redis.from_url(self.redis_url, decode_responses=True)

    async def publish(self, stream_name: str, event_data: Dict[str, Any]) -> str:
        if not self.client:
            await self.connect()
            
        payload = {"payload": json.dumps(event_data)}
        msg_id = await self.client.xadd(stream_name, payload)
        return msg_id
        
    async def close(self):
        if self.client:
            await self.client.close()