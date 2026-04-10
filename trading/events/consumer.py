import json
import redis.asyncio as redis
from typing import Dict, Any, List, Optional

class EventConsumer:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None

    async def connect(self):
        self.client = redis.Redis.from_url(self.redis_url, decode_responses=True)

    async def read_events(self, stream_name: str, group_name: str, consumer_name: str) -> List[Dict[str, Any]]:
        if not self.client:
            await self.connect()
            
        try:
            await self.client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
                
        streams = {stream_name: ">"}
        messages = await self.client.xreadgroup(group_name, consumer_name, streams, count=10, block=100)
        
        parsed_events = []
        for stream, msgs in messages:
            for msg_id, msg_data in msgs:
                if "payload" in msg_data:
                    try:
                        event = json.loads(msg_data["payload"])
                        event["_msg_id"] = msg_id
                        parsed_events.append(event)
                        # Acknowledge the message
                        await self.client.xack(stream_name, group_name, msg_id)
                    except json.JSONDecodeError:
                        pass
                        
        return parsed_events

    async def close(self):
        if self.client:
            await self.client.close()
