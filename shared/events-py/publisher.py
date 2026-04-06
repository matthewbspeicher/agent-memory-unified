import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

class EventPublisher:
    def __init__(self, redis_client, stream: str = 'events'):
        """
        Initialize the EventPublisher.
        
        Args:
            redis_client: A redis client (sync or async depending on the context).
                          This implementation assumes a standard redis-py interface.
                          If async is needed, an AsyncEventPublisher might be required.
            stream: The name of the Redis Stream to publish to.
        """
        self.redis = redis_client
        self.stream = stream

    def publish(self, event_type: str, payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Publish an event to the Redis Stream.
        
        Args:
            event_type: The type of event (e.g., 'trade.opened', 'memory.created')
            payload: Event-specific data
            metadata: Optional metadata (request_id, etc.)
        """
        if metadata is None:
            metadata = {}
            
        event = {
            'id': str(uuid.uuid4()),
            'type': event_type,
            'version': '1.0',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source': 'trading_bot',
            'payload': payload,
            'metadata': metadata,
        }
        
        # We store the entire event as a JSON string under the 'data' field,
        # mirroring the PHP implementation.
        fields = {'data': json.dumps(event)}
        
        # xadd with maxlen=10000 and approximate=True
        self.redis.xadd(
            name=self.stream,
            fields=fields,
            maxlen=10000,
            approximate=True
        )

class AsyncEventPublisher:
    def __init__(self, redis_client, stream: str = 'events'):
        """
        Initialize the AsyncEventPublisher for use with async redis libraries (like redis.asyncio).
        """
        self.redis = redis_client
        self.stream = stream

    async def publish(self, event_type: str, payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> None:
        if metadata is None:
            metadata = {}
            
        event = {
            'id': str(uuid.uuid4()),
            'type': event_type,
            'version': '1.0',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source': 'trading_bot',
            'payload': payload,
            'metadata': metadata,
        }
        
        fields = {'data': json.dumps(event)}
        
        await self.redis.xadd(
            name=self.stream,
            fields=fields,
            maxlen=10000,
            approximate=True
        )
