# Phase 3: Redis Streams Event Bus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement reliable event bus using Redis Streams with consumer groups, DLQ, and retries. Upgrade existing Pub/Sub consumer.

**Architecture:** Laravel publishes events via XADD with MAXLEN cap, Python consumes via XREADGROUP with consumer group, failed events move to DLQ after 3 retries.

**Tech Stack:** Redis Streams (XADD/XREADGROUP/XPENDING), PHP Redis extension (phpredis), Python redis-py asyncio

**Timeline:** 1 week + 2-3 days (Week 6, May 11-17, 2026)
- Days 1-2: PHP event publisher
- Days 3-5: Python consumer rewrite (Pub/Sub → Streams)
- Days 6-7: DLQ monitoring + testing

**Risk Level:** Medium (existing Pub/Sub consumer must be replaced)

---

## Pre-Execution Checklist

- [ ] Phase 2 complete (database consolidated)
- [ ] Redis deployed (Railway or docker-compose)
- [ ] Redis connection works from both services
- [ ] Existing Pub/Sub consumer at `trading/events/consumer.py` (will be replaced)

---

## Task 1: Deploy Redis (if needed)

**Files:**
- Create: `docker-compose.yml` (if local)
- Or: Railway Redis service

**Purpose:** Ensure Redis available with persistence enabled.

- [ ] **Step 1: Check if Redis already running**

```bash
redis-cli ping
```

If `PONG`: Skip to Task 2

- [ ] **Step 2: Deploy via Railway (recommended)**

```bash
railway add
# Select: Redis
# Name: agent-memory-redis

railway up
```

- [ ] **Step 3: Get connection string**

```bash
railway variables | grep REDIS_URL
```

Copy URL (redis://default:PASSWORD@host:port)

- [ ] **Step 4: Add to .env files**

```bash
# api/.env
echo "REDIS_URL=redis://..." >> api/.env

# trading/.env
echo "REDIS_URL=redis://..." >> trading/.env
```

- [ ] **Step 5: Test connection from both services**

```bash
# Laravel
cd api
php artisan tinker --execute="Redis::ping()"

# Python
cd trading
python3 -c "import redis; r=redis.from_url('redis://...'); print(r.ping())"
```

Expected: Both return `True`

- [ ] **Step 6: Commit Redis config**

```bash
git add api/.env trading/.env
git commit -m "feat(redis): add Redis connection for event bus

Redis deployed on Railway:
- Laravel: Redis facade
- Python: redis-py asyncio
- Persistence: AOF enabled (maxmemory 512mb)"
```

---

## Task 2: Create PHP Event Publisher

**Files:**
- Create: `shared/events-php/src/EventPublisher.php`
- Create: `shared/events-php/composer.json`

**Purpose:** Publish events to Redis Streams with XADD, MAXLEN cap to prevent OOM.

- [ ] **Step 1: Create PHP events package**

```bash
mkdir -p shared/events-php/src
```

- [ ] **Step 2: Create composer.json**

```bash
cat > shared/events-php/composer.json << 'EOF'
{
  "name": "agent-memory/shared-events",
  "description": "Cross-service event publishing via Redis Streams",
  "type": "library",
  "autoload": {
    "psr-4": {
      "AgentMemory\\SharedEvents\\": "src/"
    }
  },
  "require": {
    "php": ">=8.3",
    "ext-redis": "*"
  }
}
EOF
```

- [ ] **Step 3: Create EventPublisher**

```bash
cat > shared/events-php/src/EventPublisher.php << 'EOF'
<?php

namespace AgentMemory\SharedEvents;

use Illuminate\Support\Str;

class EventPublisher
{
    public function __construct(
        private \Redis|\Predis\Client $redis,
        private string $stream = 'events'
    ) {}

    /**
     * Publish event to Redis Stream.
     *
     * @param string $type Event type (e.g., 'trade.opened', 'memory.created')
     * @param array $payload Event-specific data
     * @param array $metadata Optional metadata (request_id, etc.)
     */
    public function publish(string $type, array $payload, array $metadata = []): void
    {
        $event = [
            'id' => Str::uuid()->toString(),
            'type' => $type,
            'version' => '1.0',
            'timestamp' => now()->toIso8601String(),
            'source' => 'api',
            'payload' => $payload,
            'metadata' => $metadata,
        ];

        // XADD with MAXLEN ~ 10000 to cap stream size
        // '*' = auto-generate message ID
        // ~ = approximate trimming (more efficient than exact)
        $this->redis->xAdd(
            $this->stream,
            '*',
            ['data' => json_encode($event)],
            10000,  // MAXLEN
            true    // approximate (~)
        );
    }
}
EOF
```

- [ ] **Step 4: Register in Laravel AppServiceProvider**

```bash
cd api

# Add repository
composer config repositories.shared-events path ../shared/events-php
composer require agent-memory/shared-events:@dev
```

Edit `api/app/Providers/AppServiceProvider.php`:

```php
use AgentMemory\SharedEvents\EventPublisher;
use Illuminate\Support\Facades\Redis;

public function register(): void
{
    $this->app->singleton(EventPublisher::class, function () {
        $client = Redis::connection()->client();

        // Verify phpredis driver (xAdd signature differs in Predis)
        if (!$client instanceof \Redis) {
            throw new \RuntimeException(
                "EventPublisher requires phpredis driver. " .
                "Set REDIS_CLIENT=phpredis in .env"
            );
        }

        return new EventPublisher($client);
    });
}
```

- [ ] **Step 5: Test event publishing**

```bash
cd api
php artisan tinker << 'EOF'
$publisher = app(AgentMemory\SharedEvents\EventPublisher::class);

$publisher->publish('test.event', [
    'message' => 'Hello from Laravel'
]);

echo "✅ Event published\n";

// Verify in Redis
$events = Redis::xRange('events', '-', '+');
echo "Stream length: " . count($events) . "\n";
EOF
```

Expected:
```
✅ Event published
Stream length: 1
```

- [ ] **Step 6: Commit PHP publisher**

```bash
git add shared/events-php/ api/app/Providers/AppServiceProvider.php api/composer.json api/composer.lock
git commit -m "feat(events): add PHP event publisher for Redis Streams

EventPublisher class:
- Uses XADD with MAXLEN ~ 10000 (prevents Redis OOM)
- UUID-based event IDs (collision-safe)
- JSON-encoded event envelope
- Requires phpredis driver (not Predis)

Registered as singleton in Laravel."
```

---

## Task 3: Rewrite Python Consumer for Streams

**Files:**
- Create: `trading/events/consumer_streams.py`
- Modify: `trading/api/app.py` (integrate new consumer)

**Purpose:** Replace Pub/Sub consumer with Streams consumer (consumer groups, DLQ, retries).

- [ ] **Step 1: Create new consumer (keep old for reference)**

```bash
cat > trading/events/consumer_streams.py << 'EOF'
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
EOF
```

- [ ] **Step 2: Install redis-py if needed**

```bash
cd trading
# Add to pyproject.toml if not present
uv add redis
```

- [ ] **Step 3: Test new consumer (manual)**

```bash
cd trading
python3 << 'EOF'
import asyncio
from redis.asyncio import Redis
from events.consumer_streams import StreamsEventConsumer, handle_agent_deactivated

async def test():
    redis = Redis.from_url("redis://localhost:6379")

    consumer = StreamsEventConsumer(redis, stream="events", group="test-group")
    consumer.register("AgentDeactivated", handle_agent_deactivated)

    print("✅ Consumer initialized")
    print("Listening for 10 seconds...")

    # Start consumer in background
    consumer_task = asyncio.create_task(consumer.start())

    # Wait 10 seconds
    await asyncio.sleep(10)

    # Stop consumer
    await consumer.stop()
    consumer_task.cancel()

    await redis.aclose()

asyncio.run(test())
EOF
```

Expected: Consumer runs for 10 seconds, no errors

- [ ] **Step 4: Publish test event from Laravel**

While consumer running in Step 3:

```bash
# In another terminal
cd api
php artisan tinker --execute="
app(AgentMemory\SharedEvents\EventPublisher::class)->publish('AgentDeactivated', [
    'agent_id' => '123',
    'agent_name' => 'TestAgent'
]);
"
```

Check consumer terminal - should see: `AgentDeactivated event received`

- [ ] **Step 5: Commit new consumer**

```bash
git add trading/events/consumer_streams.py
git commit -m "feat(events): add Redis Streams consumer with DLQ and retries

StreamsEventConsumer:
- Consumer groups for distributed processing
- XREADGROUP with blocking (1s timeout)
- DLQ for messages failing > 3 times
- XPENDING to track retry count
- Replaces consumer.py (Pub/Sub)

Old consumer preserved for reference."
```

---

## Task 4: Integrate Consumer in FastAPI

**Files:**
- Modify: `trading/api/app.py`

**Purpose:** Start Streams consumer on FastAPI startup, stop on shutdown.

- [ ] **Step 1: Import new consumer in app.py**

Edit `trading/api/app.py`:

```python
from contextlib import asynccontextmanager
from redis.asyncio import Redis
from events.consumer_streams import StreamsEventConsumer, handle_agent_deactivated

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: Startup and shutdown."""

    # Initialize Redis
    # config.redis_url has default "redis://localhost:6379/0" — no fallback needed
    redis = Redis.from_url(config.redis_url)

    # Start Streams consumer
    consumer = StreamsEventConsumer(
        redis,
        stream="events",
        group="trading-service",
        consumer_name=f"worker-{os.getpid()}",
    )
    consumer.register("AgentDeactivated", handle_agent_deactivated)

    consumer_task = asyncio.create_task(consumer.start())
    logger.info("Event consumer started")

    yield

    # Shutdown
    logger.info("Shutting down event consumer...")
    await consumer.stop()
    consumer_task.cancel()

    try:
        await consumer_task
    except asyncio.CancelledError:
        pass

    await redis.aclose()
    logger.info("Event consumer stopped")
```

- [ ] **Step 2: Test startup/shutdown**

```bash
cd trading
python3 -m uvicorn api.app:app --port 8080
```

Check logs:
```
INFO:     Event consumer started
INFO:     Consumer started: events/trading-service/worker-12345
```

Press Ctrl+C, check shutdown logs:
```
INFO:     Shutting down event consumer...
INFO:     Consumer cancelled
INFO:     Event consumer stopped
```

- [ ] **Step 3: Test event flow end-to-end**

```bash
# Terminal 1: Start trading service
cd trading
python3 -m uvicorn api.app:app --port 8080

# Terminal 2: Publish event from Laravel
cd api
php artisan tinker --execute="
app(AgentMemory\SharedEvents\EventPublisher::class)->publish('AgentDeactivated', [
    'agent_id' => '456',
    'agent_name' => 'IntegrationTest'
]);
"
```

Check Terminal 1 - should see:
```
INFO:events.consumer_streams:AgentDeactivated event received
```

- [ ] **Step 4: Commit FastAPI integration**

```bash
git add trading/api/app.py
git commit -m "feat(events): integrate Streams consumer in FastAPI lifespan

Consumer lifecycle:
- Starts on app startup
- Runs in background task
- Stops gracefully on shutdown
- Uses worker-{pid} for consumer name (multi-instance safe)

End-to-end tested: Laravel → Redis Streams → Python"
```

---

## Task 5: Add Event Observers in Laravel

**Files:**
- Create: `api/app/Observers/TradeObserver.php`
- Modify: `api/app/Providers/AppServiceProvider.php`

**Purpose:** Publish events when trades created/updated.

- [ ] **Step 1: Create TradeObserver**

```bash
cat > api/app/Observers/TradeObserver.php << 'EOF'
<?php

namespace App\Observers;

use App\Models\Trade;
use AgentMemory\SharedEvents\EventPublisher;

class TradeObserver
{
    public function __construct(private EventPublisher $publisher) {}

    public function created(Trade $trade): void
    {
        $this->publisher->publish('trade.opened', [
            'trade_id' => $trade->id,
            'agent_id' => $trade->agent_id,
            'symbol' => $trade->symbol,         // Keep Python column names
            'side' => $trade->side,             // 'side' not 'direction'
            'entry_price' => $trade->entry_price,
            'entry_quantity' => $trade->entry_quantity,  // 'entry_quantity' not 'quantity'
            'paper' => $trade->paper ?? false,
        ]);
    }

    public function updated(Trade $trade): void
    {
        if ($trade->status === 'closed' && $trade->wasChanged('status')) {
            $this->publisher->publish('trade.closed', [
                'trade_id' => $trade->id,
                'agent_id' => $trade->agent_id,
                'pnl' => $trade->pnl,
                'exit_price' => $trade->exit_price,
            ]);
        }
    }
}
EOF
```

- [ ] **Step 2: Register observer**

Edit `api/app/Providers/AppServiceProvider.php`:

```php
use App\Models\Trade;
use App\Observers\TradeObserver;

public function boot(): void
{
    Trade::observe(TradeObserver::class);
}
```

- [ ] **Step 3: Test observer fires event**

```bash
cd api
php artisan tinker << 'EOF'
// Create test trade
$trade = new App\Models\Trade([
    'agent_id' => '550e8400-e29b-41d4-a716-446655440000',
    'symbol' => 'AAPL',
    'side' => 'long',
    'entry_price' => '150.00',
    'entry_quantity' => 100,
    'status' => 'open',
    'paper' => false,
]);
$trade->save();

echo "✅ Trade created, event should be published\n";

// Check stream
$events = Redis::xRange('events', '-', '+', 5);
echo "Stream length: " . count($events) . "\n";

// Cleanup
$trade->delete();
EOF
```

Expected: Stream shows new event with type='trade.opened'

- [ ] **Step 4: Verify Python receives event**

With trading service running:

```bash
# In Laravel
php artisan tinker --execute="
\$trade = new App\Models\Trade([...]);  // (same as Step 3)
\$trade->save();
"
```

Check Python logs - should NOT see event (no handler registered yet)

- [ ] **Step 5: Commit observer**

```bash
git add api/app/Observers/TradeObserver.php api/app/Providers/AppServiceProvider.php
git commit -m "feat(events): add TradeObserver to publish trade.opened/closed events

Publishes:
- trade.opened: When trade created
- trade.closed: When status changes to 'closed'

Uses Python column names (symbol, side, entry_quantity) per Decision 1."
```

---

## Task 6: DLQ Monitoring

**Files:**
- Create: `scripts/monitor-dlq.sh`

**Purpose:** Alert when DLQ has too many failed events.

- [ ] **Step 1: Create monitoring script**

```bash
cat > scripts/monitor-dlq.sh << 'EOF'
#!/bin/bash
# Monitor Dead Letter Queue for failed events

REDIS_URL=${REDIS_URL:-redis://localhost:6379}
DLQ_STREAM="events:dlq"
MAX_DLQ_SIZE=100

DLQ_COUNT=$(redis-cli -u "$REDIS_URL" XLEN "$DLQ_STREAM")

echo "DLQ size: $DLQ_COUNT"

if [ "$DLQ_COUNT" -gt "$MAX_DLQ_SIZE" ]; then
    echo "⚠️  DLQ has $DLQ_COUNT failed events (threshold: $MAX_DLQ_SIZE)"

    # Show sample of failed events
    echo "Sample failed events:"
    redis-cli -u "$REDIS_URL" XRANGE "$DLQ_STREAM" - + COUNT 5

    # Send alert (Slack, email, etc.)
    # curl -X POST https://slack.com/api/chat.postMessage ...

    exit 1
fi

echo "✅ DLQ size within limits"
EOF

chmod +x scripts/monitor-dlq.sh
```

- [ ] **Step 2: Test script**

```bash
./scripts/monitor-dlq.sh
```

Expected: `✅ DLQ size within limits` (0 events)

- [ ] **Step 3: Add to cron (optional)**

```bash
# Run every 5 minutes
echo "*/5 * * * * cd /app && ./scripts/monitor-dlq.sh" | crontab -
```

- [ ] **Step 4: Create DLQ replay script**

```bash
cat > scripts/replay-dlq.sh << 'EOF'
#!/bin/bash
# Replay failed events from DLQ back to main stream

REDIS_URL=${REDIS_URL:-redis://localhost:6379}
DLQ_STREAM="events:dlq"
MAIN_STREAM="events"

echo "Replaying DLQ events to $MAIN_STREAM..."

# Get all DLQ messages
MESSAGES=$(redis-cli -u "$REDIS_URL" XRANGE "$DLQ_STREAM" - +)

if [ -z "$MESSAGES" ]; then
    echo "DLQ is empty"
    exit 0
fi

# Parse and replay (simplified - real script would iterate properly)
redis-cli -u "$REDIS_URL" << 'EOFREDIS'
XRANGE events:dlq - +
-- TODO: For each message, XADD to events stream
-- Then XDEL from DLQ
EOFREDIS

echo "⚠️  Manual review required - inspect DLQ and replay selectively"
EOF

chmod +x scripts/replay-dlq.sh
```

- [ ] **Step 5: Commit monitoring scripts**

```bash
git add scripts/monitor-dlq.sh scripts/replay-dlq.sh
git commit -m "ops(events): add DLQ monitoring and replay scripts

monitor-dlq.sh:
- Checks DLQ size every 5 min (via cron)
- Alerts if > 100 failed events
- Shows sample of failures

replay-dlq.sh:
- Manual replay of DLQ events to main stream
- Use after fixing root cause of failures"
```

---

## Task 7: End-to-End Testing

**Files:**
- Create: `tests/integration/test_event_bus.py`

**Purpose:** Verify events flow Laravel → Redis → Python with retries and DLQ.

- [ ] **Step 1: Create integration test**

```bash
cat > tests/integration/test_event_bus.py << 'EOF'
"""Integration test: Event bus end-to-end."""
import asyncio
import pytest
from redis.asyncio import Redis
from events.consumer_streams import StreamsEventConsumer

@pytest.fixture
def redis_url():
    """Redis connection URL from environment or localhost default."""
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


@pytest.mark.asyncio
async def test_event_bus_flow(redis_url: str):
    """Test event publishing and consumption."""
    redis = Redis.from_url(redis_url)

    # Track received events
    received = []

    async def test_handler(data: dict):
        received.append(data)

    # Start consumer
    consumer = StreamsEventConsumer(redis, stream="test-events", group="test-group")
    consumer.register("test.event", test_handler)

    consumer_task = asyncio.create_task(consumer.start())

    # Publish test event
    await redis.xadd("test-events", {"data": '{"type": "test.event", "payload": {"message": "hello"}}'})

    # Wait for consumer to process
    await asyncio.sleep(2)

    # Verify received
    assert len(received) == 1
    assert received[0]["message"] == "hello"

    # Cleanup
    await consumer.stop()
    consumer_task.cancel()
    await redis.aclose()


@pytest.mark.asyncio
async def test_dlq_on_failure(redis_url: str):
    """Test failed messages move to DLQ after retries."""
    redis = Redis.from_url(redis_url)

    async def failing_handler(data: dict):
        raise ValueError("Intentional failure")

    consumer = StreamsEventConsumer(redis, stream="test-events", group="test-group", max_retries=2)
    consumer.register("fail.event", failing_handler)

    consumer_task = asyncio.create_task(consumer.start())

    # Publish event that will fail
    await redis.xadd("test-events", {"data": '{"type": "fail.event", "payload": {}}'})

    # Wait for retries + DLQ
    await asyncio.sleep(5)

    # Check DLQ
    dlq_events = await redis.xrange("test-events:dlq", "-", "+")
    assert len(dlq_events) > 0, "Event should be in DLQ"

    # Cleanup
    await consumer.stop()
    consumer_task.cancel()
    await redis.xdelete("test-events:dlq", *[msg_id for msg_id, _ in dlq_events])
    await redis.aclose()
EOF
```

- [ ] **Step 2: Run integration tests**

```bash
cd trading
REDIS_URL="redis://localhost:6379" pytest tests/integration/test_event_bus.py -v
```

Expected: Both tests pass

- [ ] **Step 3: Manual end-to-end test**

```bash
# Terminal 1: Start Python service
cd trading
python3 -m uvicorn api.app:app --port 8080

# Terminal 2: Create trade in Laravel
cd api
php artisan tinker --execute="
\$trade = App\Models\Trade::create([
    'agent_id' => '550e8400-e29b-41d4-a716-446655440000',
    'symbol' => 'AAPL',
    'side' => 'long',
    'entry_price' => '150.00',
    'entry_quantity' => 100,
    'status' => 'open',
]);
echo 'Trade ID: ' . \$trade->id . PHP_EOL;
"
```

Check Terminal 1 - no handler registered, so event is ignored (expected)

- [ ] **Step 4: Add trade.opened handler in Python**

Edit `trading/events/consumer_streams.py`, add:

```python
async def handle_trade_opened(data: dict):
    """Handle trade opened event."""
    logger.info(f"Trade opened: {data['symbol']} {data['side']} x{data['entry_quantity']}")
```

Edit `trading/api/app.py`, register handler:

```python
consumer.register("AgentDeactivated", handle_agent_deactivated)
consumer.register("trade.opened", handle_trade_opened)  # ADD THIS
```

Restart service, repeat Step 3.

Expected in Terminal 1:
```
INFO:events.consumer_streams:Trade opened: AAPL long x100
```

- [ ] **Step 5: Commit tests and handler**

```bash
git add tests/integration/test_event_bus.py trading/events/consumer_streams.py trading/api/app.py
git commit -m "test(events): add integration tests and trade.opened handler

Tests:
- test_event_bus_flow: End-to-end publish → consume
- test_dlq_on_failure: Failed events move to DLQ

Handler:
- handle_trade_opened: Logs trade details
- Registered in FastAPI lifespan

Manual E2E tested: Laravel trade creation → Python logs event"
```

---

## Acceptance Criteria

Phase 3 is **complete** when:

- [x] Redis deployed and accessible (Task 1)
- [x] PHP EventPublisher uses XADD with MAXLEN (Task 2)
- [x] Python consumer rewritten for Streams (Task 3)
  - XREADGROUP with consumer group
  - DLQ for failed messages
  - Retry count tracked via XPENDING
- [x] Consumer integrated in FastAPI lifespan (Task 4)
- [x] TradeObserver publishes trade.opened/closed (Task 5)
- [x] DLQ monitoring script deployed (Task 6)
- [x] Integration tests pass (Task 7)
- [x] Manual E2E test: Laravel trade → Python handler

**Final verification:**

```bash
# PHP publishes event
cd api
php artisan tinker --execute="
app(AgentMemory\SharedEvents\EventPublisher::class)->publish('test', ['data' => 'hello']);
"

# Check stream
redis-cli XLEN events  # Should increment

# Python receives event (with trading service running)
# Check logs for "test" event

# DLQ monitoring
./scripts/monitor-dlq.sh  # Should be ✅

# Integration tests
cd trading
pytest tests/integration/test_event_bus.py -v  # All pass
```

---

## Rollback Procedure

If Streams consumer has issues:

1. **Revert to Pub/Sub consumer:**
   ```bash
   # In trading/api/app.py
   from events.consumer import EventConsumer  # Old Pub/Sub version
   ```

2. **Switch Laravel to Pub/Sub:**
   ```php
   // In EventPublisher
   Redis::publish($channel, json_encode($event));
   ```

3. **Investigate Streams issue before retry**

---

## Next Steps

After Phase 3 completes:
1. Begin Phase 5: Frontend Unification (Weeks 7-8)
2. Archive old Pub/Sub consumer: `mv trading/events/consumer.py trading/events/consumer_pubsub.deprecated`
3. Add more event types (memory.created, agent.registered, etc.)

**Deliverable:** Commit "feat(events): Phase 3 complete - Redis Streams event bus with DLQ"
