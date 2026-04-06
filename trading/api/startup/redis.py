import logging

from config import Config
from data.events import EventBus

_log = logging.getLogger(__name__)


async def setup_redis(config: Config, event_bus: EventBus, app_state) -> None:
    """Set up Redis connection and RedisSignalBridge, storing results on app_state."""

    # --- Redis Connection (for hybrid authentication and caching) ---
    if config.redis_url:
        try:
            from redis.asyncio import from_url as redis_from_url
            redis = await redis_from_url(config.redis_url, decode_responses=True)
            app_state.redis = redis
            _log.info("Redis connected for authentication")
        except ImportError:
            _log.warning("redis-py not installed — authentication will fail")
        except Exception as redis_exc:
            _log.warning("Redis connection failed: %s", redis_exc)

    # --- Redis Signal Bridge (Track 20) ---
    if config.redis_url:
        try:
            from data.redis_bridge import RedisSignalBridge

            node_id = "oracle" if config.worker_mode else "primary"
            redis_bridge = RedisSignalBridge(
                event_bus=event_bus, redis_url=config.redis_url, node_id=node_id
            )
            await redis_bridge.start()
            app_state.redis_bridge = redis_bridge
        except ImportError:
            _log.warning(
                "redis-py not installed — distributed signal bridge disabled"
            )
        except Exception as rb_exc:
            _log.warning("RedisSignalBridge startup failed: %s", rb_exc)
