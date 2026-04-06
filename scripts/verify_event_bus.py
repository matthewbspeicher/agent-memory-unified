import asyncio
import json
from uuid import uuid4
from datetime import datetime, timezone
import redis.asyncio as redis

async def run_test():
    print("🚀 Running Event Bus Integration Test...")
    
    # 1. Connect to Redis
    r = redis.Redis.from_url("redis://localhost:6379/0")
    
    agent_id = "019d63a2-192f-7188-9108-d0f78ed25ed8"

    # 2. Create a synthetic AgentRegistered event to ensure the FK passes
    agent_event_id = str(uuid4())
    agent_payload = {
        "id": agent_event_id,
        "type": "agent.registered",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "integration-test-script",
        "data": {
            "id": agent_id,
            "name": "Integration Test Agent",
            "owner_id": "test-owner-123",
            "is_active": True
        }
    }
    
    print(f"📡 Publishing agent.registered event: {agent_event_id}...")
    await r.xadd("events", {"data": json.dumps(agent_payload)}, maxlen=10000, approximate=True)
    
    # Give the consumer a second to process the agent
    await asyncio.sleep(2)

    # 3. Create a synthetic TradeExecuted event
    event_id = str(uuid4())
    event_payload = {
        "id": event_id,
        "type": "trade.executed",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "integration-test-script",
        "data": {
            "agent_id": agent_id,
            "agent_name": "Integration Test Agent",
            "symbol": "BTCUSD",
            "side": "long",
            "entry_price": "65000.00",
            "entry_quantity": 2,
            "status": "open",
            "entry_time": datetime.now(timezone.utc).isoformat(),
        }
    }
    
    print(f"📡 Publishing trade.executed event: {event_id} to stream 'events'...")
    await r.xadd("events", {"data": json.dumps(event_payload)}, maxlen=10000, approximate=True)
    
    messages = await r.xrevrange("events", max="+", min="-", count=2)
    print(f"Check Redis Output: {messages}")
    print("✅ Events published successfully!")
    print("   Run `php artisan queue:work` or check your Laravel consumers to verify ingestion.")
    
    await r.aclose()

if __name__ == "__main__":
    asyncio.run(run_test())
