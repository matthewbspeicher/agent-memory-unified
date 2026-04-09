import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class TradingViewContextFetcher:
    def __init__(self, redis_client: Any):
        self.redis = redis_client
        
    async def get_latest_chart_context(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.redis:
            return None
            
        try:
            # Read the latest message from the stream
            messages = await self.redis.xrevrange('tradingview_charts', count=5)
            for msg_id, fields in messages:
                data_str = fields.get(b'data', b'{}').decode('utf-8')
                data = json.loads(data_str)
                if data.get('symbol') == symbol:
                    return data
            return None
        except Exception as e:
            logger.error(f"Failed to fetch TradingView context: {e}")
            return None