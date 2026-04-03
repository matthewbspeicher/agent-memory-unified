# Codebase Unification Design — agent-memory + stock-trading-api

**Date:** 2026-04-02
**Status:** Revised (v2) — Critical issues from review addressed
**Strategy:** Approach 2 (Balanced Integration)
**Timeline:** 7 weeks (extended from 5 weeks)
**Team:** 2 developers, parallel workstreams
**Phase 3 Complete:** ✅ Redis Streams event bus already implemented in stock-trading-api

---

## Revision History

**v2 (2026-04-02 PM):** Addressed critical code review findings:
- C1: Auth now hybrid (existing token hashing + optional JWT)
- C2: Acknowledged 30+ SQLite tables, full migration plan
- C3: Explicit `tracked_positions` → new `trades` schema mapping
- C4: Python `agent_registry` → `trading_strategies` rename
- C5: PostgreSQL consolidation (not greenfield migration)
- H2: MAXLEN increased to 100,000
- H3: Fixed `xpending_range` key name bug
- H7: Frontend timeline extended to 3 weeks
- Phase 3 already complete, Phase 0 added for internal hardening

**v1 (2026-04-02 AM):** Initial specification

---

## Executive Summary

**Goal:** Merge `agent-memory` (Laravel/PHP memory API) and `stock-trading-api` (FastAPI/Python trading engine) into a unified polyglot monorepo with shared types, event-driven communication, and consolidated infrastructure.

**Why Now:**
- Both projects have overlapping concerns (agents, LLM services, storage, auth)
- Duplication causes data drift (agent models out of sync between services)
- Integration via external API calls adds latency and operational complexity
- Single deployment pipeline reduces infrastructure overhead

**What Changes:**
- **Repository:** Two separate repos → One monorepo with `api/`, `trading/`, `frontend/`
- **Database:** SQLite + separate PostgreSQL → Single PostgreSQL with service-owned tables
- **Frontend:** Vue+Inertia + React SPA → Unified React SPA
- **Communication:** External API calls → Internal service mesh + Redis Streams event bus
- **Types:** Duplicated models → Shared JSON Schema → generated code (Python/PHP/TypeScript)

**What Stays The Same:**
- Laravel continues to own memory/agent management
- FastAPI continues to own trading execution
- Both services can run independently (no tight coupling)
- Incremental migration (zero downtime)

---

## Architecture Overview

### Service Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                      PostgreSQL (Unified)                    │
├─────────────────────────────────────────────────────────────┤
│  Laravel-Owned Tables:                                       │
│  • users, agents, memories, memory_shares, workspaces        │
│  • achievements, arena_profiles, arena_matches               │
│                                                               │
│  Python-Owned Tables (30+ total, key ones listed):           │
│  • trades, tracked_positions, trading_stats, opportunities   │
│  • trading_strategies (renamed from agent_registry)          │
│  • execution_quality, shadow_executions, arb_spreads         │
│  • signal_features, trade_analytics, performance_snapshots   │
│  • bittensor_* (4 tables), consensus_*, tournaments          │
│                                                               │
│  Migration Ownership: ALL DDL via Laravel migrations         │
│  Note: Some tables remain local SQLite (ephemeral/cache)     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Redis Streams (Event Bus)                 │
├─────────────────────────────────────────────────────────────┤
│  Events: trade.opened, trade.closed, memory.created,         │
│          agent.registered, agent.deactivated                 │
│                                                               │
│  Consumers: Laravel (leaderboard, achievements)              │
│             Python (journal indexing, agent init)            │
│                                                               │
│  Reliability: Consumer groups, XACK, DLQ, MAXLEN cap         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      Services (Kubernetes)                   │
├─────────────────────────────────────────────────────────────┤
│  api:8000        → Laravel (Memory API, Auth, Public Feed)   │
│  trading:8080    → FastAPI (Execution, Broker Adapters)      │
│  frontend:3000   → React SPA (Vite, unified UI)              │
│                                                               │
│  Communication:                                              │
│  • Sync: HTTP calls via internal k8s DNS                     │
│  • Async: Redis Streams pub/sub                             │
│  • Auth: Shared JWT secret + Redis blacklist                │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow Examples

**Trade Execution → Leaderboard Update:**
```
1. User opens trade via frontend
2. Frontend → FastAPI /trades POST
3. Python validates agent (SELECT from agents table)
4. Python inserts trade, publishes trade.opened event to Redis
5. Laravel consumes event, updates arena_profiles.trading_score
6. Laravel checks achievement triggers (first_trade, win_streak)
7. Frontend polls /arena/leaderboard, sees updated ranking
```

**Memory Creation → Journal Indexing:**
```
1. Agent stores memory via API
2. Laravel creates memory record, generates embedding (pgvector)
3. Laravel publishes memory.created event
4. Python consumes event, indexes in local HNSW for fast journal search
5. Python agent queries journal for similar past trades
```

---

## Section 1: Monorepo Structure

```
agent-memory/                        # Unified repo (new name)
├── api/                             # Laravel 12 (Memory API)
│   ├── app/
│   │   ├── Models/                 # Eloquent models (Agent, Memory, User)
│   │   ├── Services/               # SummarizationService, EmbeddingService
│   │   ├── Http/Controllers/Api/
│   │   └── Observers/
│   ├── database/
│   │   └── migrations/             # ALL database migrations (PHP + Python tables)
│   ├── routes/api.php
│   ├── tests/
│   └── composer.json
│
├── trading/                         # FastAPI (Trading Engine)
│   ├── adapters/                   # IBKR, Kalshi, Polymarket
│   ├── agents/                     # Strategy framework, runner, router
│   ├── api/                        # FastAPI routes
│   ├── storage/                    # DB connection, stores (no migrations)
│   ├── strategies/                 # RSI, volume_spike, kalshi_news_arb
│   ├── risk/                       # RiskEngine, kill-switch
│   ├── learning/                   # TradeReflector, memory_client
│   ├── whatsapp/                   # Assistant bot
│   ├── tests/
│   └── requirements.txt
│
├── frontend/                        # React 19 + Vite (Unified UI)
│   ├── src/
│   │   ├── pages/
│   │   │   ├── landing/           # Public landing, pricing
│   │   │   ├── auth/              # Login, register
│   │   │   ├── dashboard/         # Authenticated dashboard
│   │   │   ├── memories/          # Memory feed, search, detail
│   │   │   ├── trading/           # Trading dashboard, positions, journal
│   │   │   ├── arena/             # Battle arena, leaderboard
│   │   │   └── public/            # Commons feed, agent profiles
│   │   ├── components/
│   │   │   ├── memories/          # MemoryCard, MemoryFeed, MemorySearch
│   │   │   ├── trading/           # TradeCard, EquityCurve, PositionTable
│   │   │   ├── arena/             # MatchCard, Leaderboard
│   │   │   └── layout/            # Header, Sidebar, Footer
│   │   ├── lib/
│   │   │   ├── api/
│   │   │   │   ├── memory.ts      # Laravel API client
│   │   │   │   ├── trading.ts     # FastAPI client
│   │   │   │   └── client.ts      # Base axios client with auth
│   │   │   ├── auth/
│   │   │   │   ├── AuthContext.tsx
│   │   │   │   └── useAuth.ts
│   │   │   └── hooks/             # useMemories, useTrades, useWebSocket
│   │   ├── types/                 # Re-exports from shared/types
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── router.tsx             # React Router v7 config
│   └── package.json
│
├── shared/                          # Cross-service abstractions
│   ├── types/
│   │   ├── schemas/                # JSON Schema (source of truth)
│   │   │   ├── agent.schema.json
│   │   │   ├── memory.schema.json
│   │   │   ├── trade.schema.json
│   │   │   └── event.schema.json
│   │   ├── generated/
│   │   │   ├── python/            # Pydantic models (auto-generated)
│   │   │   ├── typescript/        # TS types (auto-generated)
│   │   │   └── php/               # PHP DTOs (auto-generated)
│   │   └── package.json           # @agent-memory/types
│   │
│   ├── events/                     # Redis Streams event bus
│   │   ├── publisher.py           # Python EventPublisher
│   │   ├── consumer.py            # Python ReliableConsumer
│   │   ├── publisher.php          # PHP EventPublisher
│   │   └── schemas/               # Event JSON schemas
│   │       ├── trade_opened.json
│   │       ├── trade_closed.json
│   │       ├── memory_created.json
│   │       └── agent_updated.json
│   │
│   ├── auth/                       # JWT validation
│   │   ├── validate.py            # Python JWT + blacklist check
│   │   └── JWTValidator.php       # PHP JWT validator
│   │
│   └── ui/                         # Shared React components
│       ├── TradingCard.tsx
│       ├── MemoryCard.tsx
│       ├── StatsWidget.tsx
│       └── package.json           # @agent-memory/ui
│
├── k8s/                            # Kubernetes manifests
│   ├── base/
│   │   ├── api-deployment.yaml
│   │   ├── trading-deployment.yaml
│   │   ├── frontend-deployment.yaml
│   │   ├── postgres.yaml
│   │   ├── redis.yaml
│   │   └── pgbouncer.yaml
│   └── overlays/
│       ├── dev/
│       ├── staging/
│       └── production/
│
├── scripts/                        # Dev & ops scripts
│   ├── dev-setup.sh               # One-command local dev start
│   ├── sync-types.sh              # Generate types from JSON Schema
│   ├── migrate-db.sh              # Run Laravel migrations
│   ├── migrate-trading-data.py    # SQLite → PostgreSQL migration
│   └── monitor-dlq.py             # Check Redis DLQ for failed events
│
├── docs/
│   ├── architecture/
│   ├── api/                       # OpenAPI specs
│   ├── superpowers/               # Existing specs & plans
│   └── runbooks/
│
├── .github/
│   └── workflows/
│       ├── api-ci.yml             # Laravel tests, type-check
│       ├── trading-ci.yml         # Python tests, type-check
│       ├── frontend-ci.yml        # React tests, build
│       └── shared-types-check.yml # Verify generated types committed
│
├── docker-compose.yml              # Local dev orchestration
├── .env.example                   # Unified environment template
├── pyproject.toml                 # uv workspace config
└── README.md
```

### Key Principles

1. **Service Independence:** Each service has its own dependencies, can run standalone
2. **Shared Layer is Opt-In:** Services aren't forced to use `shared/`, it eliminates duplication where it helps
3. **Language-Specific Tooling:** Composer in `api/`, uv/pip in `trading/`, npm in `frontend/`
4. **Single Source of Truth:** JSON Schema → generated code, not hand-maintained duplicates
5. **Deploy Independently:** Each service has its own k8s deployment, scales separately

---

## Section 2: Shared Models & Type System

### Source of Truth: JSON Schema

All core entities are defined as JSON Schema documents in `shared/types/schemas/`. These are the **canonical definitions** — all code is generated from them.

**Example: `agent.schema.json`**
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "title": "Agent",
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique agent identifier"
    },
    "name": {
      "type": "string",
      "maxLength": 255,
      "description": "Agent display name"
    },
    "token_hash": {
      "type": "string",
      "description": "SHA256 hash of agent token (amc_*)"
    },
    "is_active": {
      "type": "boolean",
      "description": "Whether agent can make API calls"
    },
    "scopes": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Permitted operations (memories:write, trading:execute)"
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time"
    }
  },
  "required": ["id", "name", "token_hash", "is_active"]
}
```

### Code Generation Pipeline

**`scripts/sync-types.sh`** (runs on pre-commit hook + CI):
```bash
#!/bin/bash
set -e

echo "🔄 Generating types from JSON Schema..."

# Python: Generate Pydantic models
datamodel-codegen \
  --input shared/types/schemas/ \
  --output shared/types/generated/python/ \
  --output-model-type pydantic_v2.BaseModel \
  --use-standard-collections \
  --field-constraints

# TypeScript: Generate types
quicktype \
  --src shared/types/schemas/ \
  --out shared/types/generated/typescript/index.ts \
  --lang typescript \
  --just-types

# PHP: Generate DTOs (custom script)
php artisan types:generate

echo "✅ Types synchronized"
```

### Usage in Services

**Python (FastAPI):**
```python
from shared_types import Agent, Trade, Memory

@router.get("/agents/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str):
    row = await db.fetch_one(
        "SELECT * FROM agents WHERE id = $1",
        agent_id
    )
    return Agent(**row)  # Type-safe validation
```

**PHP (Laravel):**
```php
use AgentMemory\SharedTypes\Agent;
use AgentMemory\SharedTypes\Trade;

// Type-safe validation
$validated = $request->validate(Agent::validationRules());
$agent = Agent::fromArray($validated);

// Convert to Eloquent model
$eloquentAgent = \App\Models\Agent::find($agent->id);
```

**TypeScript (Frontend):**
```typescript
import { Agent, Trade, Memory } from '@agent-memory/types';

const fetchAgent = async (id: string): Promise<Agent> => {
  const res = await memoryClient.get<Agent>(`/agents/${id}`);
  return res.data;
};
```

### Core Types

**Priority 1 (Cross-service):**
- `Agent` — Identity used by both services
- `Memory` — Stored knowledge
- `Trade` — Execution record
- `Position` — Current holdings
- `TradingStats` — Performance metrics

**Priority 2 (API contracts):**
- `CreateMemoryRequest` / `CreateMemoryResponse`
- `SearchMemoriesRequest` / `SearchMemoriesResponse`
- `CreateTradeRequest` / `CreateTradeResponse`
- Error response schemas

**Priority 3 (Events):**
- Base `Event` type (id, type, version, timestamp, source, payload)
- Specific event payloads (TradeOpenedPayload, MemoryCreatedPayload)

### Type Sync Workflow

1. **Developer changes schema:** Edit `agent.schema.json`, add new field
2. **Pre-commit hook runs:** `scripts/sync-types.sh` regenerates all types
3. **Type errors surface immediately:** TypeScript/PHP/Python compilers catch drift
4. **CI enforces:** PR fails if generated types aren't committed

**Critical Rule:** Generated types are **read-only DTOs**. Business logic lives in service-specific models (`api/app/Models/Agent.php` for Eloquent, `trading/agents/models.py` for domain logic).

---

## Section 3: Event Bus Architecture

### Design Philosophy

**Eventual Consistency via Redis Streams:** Services publish domain events (trade closed, memory created) to Redis, other services consume asynchronously. This decouples services — trading engine doesn't need to wait for Laravel to update the leaderboard before returning a response.

**Reliability First:** Redis Streams is in-memory and loses data if consumers crash. We add:
- **Consumer Groups:** Multiple workers can process events in parallel
- **XACK:** Workers explicitly acknowledge successful processing
- **XCLAIM:** Reclaim messages from dead workers
- **DLQ (Dead Letter Queue):** Poison pills don't halt the system
- **MAXLEN:** Cap stream length to prevent OOM

### Event Schema Structure

All events follow this base structure:

```json
{
  "id": "01J1234567890ABCDEF",
  "type": "trade.closed",
  "version": "1.0",
  "timestamp": "2026-04-02T18:30:00Z",
  "source": "trading-engine",
  "payload": {
    "trade_id": "uuid",
    "agent_id": "uuid",
    "pnl": 650.00,
    "pnl_percent": 3.51
  },
  "metadata": {
    "correlation_id": "request-trace-id",
    "causation_id": "parent-event-id"
  }
}
```

### Key Events

**1. `trade.opened`** (Python → Laravel)
```json
{
  "type": "trade.opened",
  "payload": {
    "trade_id": "uuid",
    "agent_id": "uuid",
    "ticker": "AAPL",
    "direction": "long",
    "entry_price": 185.50,
    "quantity": 100,
    "paper": true,
    "strategy": "rsi_scanner",
    "decision_memory_id": "uuid"
  }
}
```
**Consumers:**
- Laravel: Updates `arena_profiles.trading_score`
- Laravel: Checks achievement triggers (`first_trade`)

**2. `trade.closed`** (Python → Laravel)
```json
{
  "type": "trade.closed",
  "payload": {
    "trade_id": "uuid",
    "agent_id": "uuid",
    "pnl": 650.00,
    "pnl_percent": 3.51,
    "exit_price": 192.00,
    "outcome_memory_id": "uuid"
  }
}
```
**Consumers:**
- Laravel: Recalculates leaderboard ranking
- Laravel: Checks achievement triggers (win streak, profit milestones)
- Laravel: Sends notification email if crossed threshold

**3. `memory.created`** (Laravel → Python)
```json
{
  "type": "memory.created",
  "payload": {
    "memory_id": "uuid",
    "agent_id": "uuid",
    "value": "Identified bearish divergence on SPY...",
    "type": "lesson",
    "tags": ["SPY", "technical-analysis"],
    "visibility": "public"
  }
}
```
**Consumers:**
- Python: Updates local HNSW vector index for journal search
- Python: If tagged with ticker agent is trading, enriches market context

**4. `agent.registered`** (Laravel → Python)
```json
{
  "type": "agent.registered",
  "payload": {
    "agent_id": "uuid",
    "name": "AlphaBot",
    "scopes": ["memories:write", "trading:execute"],
    "owner_id": "uuid"
  }
}
```
**Consumers:**
- Python: Creates local agent record in SQLite (for offline operation)
- Python: Initializes risk limits, position tracking

**5. `agent.deactivated`** (Laravel → Python)
```json
{
  "type": "agent.deactivated",
  "payload": {
    "agent_id": "uuid",
    "reason": "user_requested"
  }
}
```
**Consumers:**
- Python: Adds `agent_id` to Redis blacklist (revoke in-flight JWTs)
- Python: Closes all open positions in paper mode
- Laravel: Updates arena profile to inactive

### Implementation: Publisher

**PHP Publisher** (`shared/events/EventPublisher.php`):
```php
<?php

namespace Shared\Events;

use Predis\Client;
use Illuminate\Support\Str;

class EventPublisher
{
    private Client $redis;
    private string $stream;

    public function __construct(Client $redis, string $stream = 'events')
    {
        $this->redis = $redis;
        $this->stream = $stream;
    }

    public function publish(string $type, array $payload, array $metadata = []): string
    {
        $event = [
            'id' => Str::uuid(),
            'type' => $type,
            'version' => '1.0',
            'timestamp' => now()->toIso8601String(),
            'source' => 'memory-api',
            'payload' => json_encode($payload),
            'metadata' => json_encode($metadata),
        ];

        // CRITICAL: Cap stream length to prevent Redis OOM
        // MAXLEN ~ 100000 means keep last ~100k events (approximate trimming)
        $id = $this->redis->xadd(
            $this->stream,
            'MAXLEN', '~', 10000,  // Trim to ~100k events
            '*',  // Auto-generate ID
            $event
        );

        \Log::info("Published event: {$type}", ['id' => $id]);
        return $id;
    }
}
```

**Python Publisher** (`shared/events/publisher.py`):
```python
import json
import uuid
from datetime import datetime, timezone
from redis.asyncio import Redis

class EventPublisher:
    def __init__(self, redis: Redis, stream: str = "events"):
        self.redis = redis
        self.stream = stream

    async def publish(self, event_type: str, payload: dict, metadata: dict = None) -> str:
        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "trading-engine",
            "payload": json.dumps(payload),
            "metadata": json.dumps(metadata or {}),
        }

        # MAXLEN ~ 100000: keep last ~100k events
        event_id = await self.redis.xadd(
            self.stream,
            event,
            maxlen=10000,
            approximate=True
        )

        logger.info(f"Published event: {event_type}", extra={"event_id": event_id})
        return event_id
```

### Implementation: Consumer (Hardened)

**Python Consumer** (`shared/events/consumer.py`):
```python
import asyncio
import json
import logging
from typing import Callable, Dict
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

class ReliableConsumer:
    """Redis Streams consumer with reliability guarantees."""

    def __init__(
        self,
        redis: Redis,
        stream: str = "events",
        group: str = "trading-service",
        consumer: str = "worker-1"
    ):
        self.redis = redis
        self.stream = stream
        self.group = group
        self.consumer = consumer
        self.handlers: Dict[str, Callable] = {}
        self.max_retries = 3

    def register(self, event_type: str, handler: Callable):
        """Register a handler for an event type."""
        self.handlers[event_type] = handler

    async def start(self):
        """Start consuming events."""
        # Create consumer group if it doesn't exist
        try:
            await self.redis.xgroup_create(
                self.stream, self.group, id="0", mkstream=True
            )
            logger.info(f"Created consumer group: {self.group}")
        except Exception as e:
            # Group already exists
            logger.info(f"Consumer group exists: {self.group}")

        logger.info(f"Starting consumer: {self.consumer} in group {self.group}")

        while True:
            try:
                # Read new messages
                messages = await self.redis.xreadgroup(
                    self.group,
                    self.consumer,
                    {self.stream: ">"},
                    count=10,
                    block=5000  # 5 second timeout
                )

                for stream, events in messages:
                    for event_id, data in events:
                        await self._handle_event(event_id, data)

                # Reclaim stale messages from crashed workers
                await self._reclaim_pending()

            except Exception as e:
                logger.error(f"Consumer error: {e}")
                await asyncio.sleep(5)

    async def _handle_event(self, event_id: str, data: dict):
        """Handle a single event with retry logic."""
        event_type = data[b"type"].decode()
        payload = json.loads(data[b"payload"].decode())

        # Check retry count via XPENDING
        info = await self.redis.xpending_range(
            self.stream, self.group, event_id, event_id, count=1
        )
        retry_count = info[0]["num_deliveries"] if info else 0  # redis-py uses num_deliveries, not times_delivered

        if retry_count >= self.max_retries:
            # Move to Dead Letter Queue
            await self.redis.xadd("events:dlq", "*", data)
            await self.redis.xack(self.stream, self.group, event_id)
            logger.error(
                f"Event {event_id} moved to DLQ after {retry_count} retries",
                extra={"event_type": event_type, "payload": payload}
            )
            return

        try:
            # Call registered handler
            if event_type in self.handlers:
                await self.handlers[event_type](payload)
            else:
                logger.warning(f"No handler for event type: {event_type}")

            # ACK on success
            await self.redis.xack(self.stream, self.group, event_id)
            logger.info(f"Processed event: {event_type}", extra={"event_id": event_id})

        except Exception as e:
            logger.error(
                f"Handler failed for {event_type}: {e}",
                extra={"event_id": event_id, "retry_count": retry_count},
                exc_info=True
            )
            # Don't ACK - message stays in Pending Entries List for retry

    async def _reclaim_pending(self):
        """Reclaim messages from dead/crashed workers."""
        pending = await self.redis.xpending(self.stream, self.group)
        if pending["pending"] == 0:
            return

        # Reclaim messages idle > 60 seconds
        idle_threshold = 60000  # milliseconds
        claimed = await self.redis.xclaim(
            self.stream,
            self.group,
            self.consumer,
            min_idle_time=idle_threshold,
            count=10
        )

        if claimed:
            logger.info(f"Reclaimed {len(claimed)} stale messages")
            for event_id, data in claimed:
                await self._handle_event(event_id, data)
```

**Usage in Trading Service:**
```python
# trading/api/events.py
from shared.events.consumer import ReliableConsumer
from redis.asyncio import Redis

redis = Redis.from_url(settings.redis_url)
consumer = ReliableConsumer(redis, stream="events", group="trading-service", consumer="worker-1")

@consumer.register("memory.created")
async def on_memory_created(payload: dict):
    """Index memory in local vector store."""
    await journal_indexer.add(
        memory_id=payload["memory_id"],
        text=payload["value"],
        tags=payload["tags"]
    )

@consumer.register("agent.registered")
async def on_agent_registered(payload: dict):
    """Initialize agent in trading system."""
    await agent_store.create_local(
        agent_id=payload["agent_id"],
        name=payload["name"]
    )

@consumer.register("agent.deactivated")
async def on_agent_deactivated(payload: dict):
    """Revoke agent's JWT tokens."""
    agent_id = payload["agent_id"]
    await redis.sadd(f"revoked_tokens:{agent_id}", "*")
    await redis.expire(f"revoked_tokens:{agent_id}", 900)  # 15min TTL

# Start consumer in background
asyncio.create_task(consumer.start())
```

### Monitoring & Operations

**Dead Letter Queue Monitor** (`scripts/monitor-dlq.py`):
```python
import asyncio
from redis.asyncio import Redis

async def check_dlq():
    redis = Redis.from_url(os.getenv("REDIS_URL"))
    dlq_count = await redis.xlen("events:dlq")

    if dlq_count > 100:
        # Alert via Slack/PagerDuty
        await send_alert(
            f"⚠️ DLQ has {dlq_count} failed events!",
            severity="high"
        )

    # Log sample events
    if dlq_count > 0:
        events = await redis.xrange("events:dlq", count=10)
        for event_id, data in events:
            logger.error("DLQ event", extra={"event": data})

if __name__ == "__main__":
    asyncio.run(check_dlq())
```

**Run as cron:** `*/5 * * * * /app/scripts/monitor-dlq.py`

**Grafana Dashboard Metrics:**
- Stream length: `XLEN events`
- Pending messages per group: `XPENDING events <group>`
- DLQ length: `XLEN events:dlq`
- Consumer lag: timestamp of oldest message in PEL

---

## Section 4: Database Schema Consolidation

### Critical Decision: Laravel Owns All Migrations

**Rationale:**
- Single source of truth for schema (no drift between Alembic and Eloquent)
- Eloquent migrations are battle-tested and declarative
- Python services just connect and use the schema Laravel creates
- If Python needs a new table, we add it to `api/database/migrations/`

**Alternative Rejected:** Letting both services manage their own migrations leads to:
- Race conditions (both services ALTER same table)
- Schema drift (Python expects column that Laravel didn't create)
- Deployment coordination nightmares

### Service Ownership & Access Matrix

```sql
-- Database users
CREATE USER laravel_app WITH PASSWORD '...';
CREATE USER trading_app WITH PASSWORD '...';

-- Laravel owns all DDL (Data Definition Language)
GRANT ALL PRIVILEGES ON SCHEMA public TO laravel_app;
GRANT CREATE ON DATABASE agent_memory TO laravel_app;

-- Python: Read-only access to Laravel tables
GRANT SELECT ON users, agents, workspaces, memories TO trading_app;

-- Python: Full access to its own tables
GRANT SELECT, INSERT, UPDATE, DELETE ON trades, positions, trading_stats, opportunities, execution_quality TO trading_app;

-- Laravel: Read-only access to Python tables (for leaderboard)
GRANT SELECT ON trades, trading_stats, positions TO laravel_app;
```

### Schema Layout

**Laravel-Owned Tables:**
```sql
-- api/database/migrations/..._create_agents_table.php
CREATE TABLE agents (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT TRUE,
    scopes JSONB,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- api/database/migrations/..._create_memories_table.php
CREATE TABLE memories (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL,
    value TEXT NOT NULL,
    type VARCHAR(50),
    embedding VECTOR(1536),  -- pgvector
    visibility VARCHAR(20) DEFAULT 'private',
    created_at TIMESTAMP NOT NULL
);

-- Plus: users, workspaces, memory_shares, achievements, arena_profiles, arena_matches
```

**Python-Owned Tables (Created by Laravel Migration):**

**Critical Note (C3):** The new `trades` schema below is **different** from the SQLite `tracked_positions` table. The migration script (Phase 2, step 6) performs explicit column mapping:
- `symbol` → `ticker`
- `side` → `direction`
- `agent_name` (TEXT) → `agent_id` (UUID via lookup)
- INTEGER primary key → UUID
- TEXT decimals → proper DECIMAL types

```php
// api/database/migrations/2026_04_03_000001_create_trading_tables.php

public function up()
{
    Schema::create('trades', function (Blueprint $table) {
        $table->uuid('id')->primary();
        $table->uuid('agent_id');
        $table->uuid('parent_trade_id')->nullable();
        $table->string('ticker', 64);
        $table->enum('direction', ['long', 'short']);
        $table->decimal('entry_price', 24, 8);
        $table->decimal('quantity', 24, 8);
        $table->decimal('fees', 24, 8)->default(0);
        $table->timestamp('entry_at');
        $table->timestamp('exit_at')->nullable();
        $table->enum('status', ['open', 'closed', 'cancelled'])->default('open');
        $table->decimal('pnl', 24, 8)->nullable();
        $table->decimal('pnl_percent', 8, 4)->nullable();
        $table->string('strategy')->nullable();
        $table->float('confidence')->nullable();
        $table->boolean('paper')->default(true);
        $table->uuid('decision_memory_id')->nullable();
        $table->uuid('outcome_memory_id')->nullable();
        $table->jsonb('metadata')->nullable();
        $table->timestamps();

        // Indexes for performance
        $table->index(['agent_id', 'status']);
        $table->index(['agent_id', 'ticker', 'paper']);
        $table->index(['agent_id', 'paper', 'entry_at']);
    });

    Schema::create('positions', function (Blueprint $table) {
        $table->uuid('id')->primary();
        $table->uuid('agent_id');
        $table->string('ticker', 64);
        $table->boolean('paper');
        $table->decimal('quantity', 24, 8);
        $table->decimal('avg_entry_price', 24, 8);
        $table->timestamp('updated_at');

        $table->unique(['agent_id', 'ticker', 'paper']);
    });

    Schema::create('trading_stats', function (Blueprint $table) {
        $table->uuid('id')->primary();
        $table->uuid('agent_id');
        $table->boolean('paper');
        $table->integer('total_trades')->default(0);
        $table->integer('win_count')->default(0);
        $table->integer('loss_count')->default(0);
        $table->decimal('win_rate', 5, 2)->nullable();
        $table->decimal('profit_factor', 10, 4)->nullable();
        $table->decimal('total_pnl', 24, 8)->default(0);
        $table->decimal('avg_pnl_percent', 8, 4)->nullable();
        $table->decimal('best_trade_pnl', 24, 8)->nullable();
        $table->decimal('worst_trade_pnl', 24, 8)->nullable();
        $table->decimal('sharpe_ratio', 8, 4)->nullable();
        $table->integer('current_streak')->default(0);
        $table->timestamp('updated_at');

        $table->unique(['agent_id', 'paper']);
    });

    // C4 fix: Renamed from agent_registry to disambiguate from Laravel's agents table
    Schema::create('trading_strategies', function (Blueprint $table) {
        $table->id();  // Serial primary key (Python agents framework expects this)
        $table->uuid('laravel_agent_id');  // FK to agents.id
        $table->string('name')->unique();  // "rsi_scanner", "kalshi_arb"
        $table->string('strategy_type');  // "rsi", "volume_spike", "kalshi_news_arb"
        $table->string('schedule');  // "continuous", "cron"
        $table->jsonb('universe')->nullable();  // ["AAPL", "MSFT"]
        $table->jsonb('parameters')->nullable();  // Strategy-specific config
        $table->float('trust_level')->default(0.0);
        $table->boolean('shadow_mode')->default(false);
        $table->integer('generation')->default(0);
        $table->timestamps();

        $table->foreign('laravel_agent_id')->references('id')->on('agents')->onDelete('cascade');
    });
}
```

### Cross-Service Access Patterns

**Pattern 1: Direct Read (Fast Path)**
```python
# Python needs agent name for notification
agent = await db.fetch_one(
    "SELECT name, is_active FROM agents WHERE id = $1",
    agent_id
)
```
**Rules:**
- Read-only queries
- No joins across service boundaries (Python doesn't JOIN trades + memories)
- Cache aggressively (agent names rarely change)

**Pattern 2: Write via API (Slow Path)**
```python
# Python wants to trigger a webhook (Laravel owns webhooks)
await memory_client.post('/internal/webhooks/trigger', {
    'agent_id': agent_id,
    'event': 'trade.closed',
    'payload': {...}
})
```
**Rules:**
- Any write to another service's tables goes through owning service's API
- Never direct SQL INSERT/UPDATE to another service's tables

**Pattern 3: Async via Events (Eventual Consistency)**
```python
# Python closes trade
await trade_store.update(trade_id, status='closed', pnl=650)
await event_publisher.publish('trade.closed', payload)

# Laravel handles event 100-500ms later
# Updates leaderboard, checks achievements
```
**Rules:**
- Non-critical updates (analytics, denormalized caches)
- System remains available even if event processing lags

### No Foreign Keys Across Services

```sql
-- ❌ BAD: PHP table references Python table
CREATE TABLE achievements (
    trade_id UUID REFERENCES trades(id)  -- trades owned by Python!
);

-- ✅ GOOD: Soft reference, validate via application logic
CREATE TABLE achievements (
    trade_id UUID,
    CHECK (trade_id IS NOT NULL)
);
```

**Referential integrity via application:**
```python
@router.post("/trades")
async def create_trade(trade: TradeCreate):
    # Validate agent exists (SELECT from agents table)
    agent = await db.fetch_one("SELECT id FROM agents WHERE id = $1 AND is_active = TRUE", trade.agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found or inactive")

    # Now safe to insert
    return await trade_store.create(trade)
```

### Connection Pooling

**Development:** Direct connections (low concurrency, simple debugging)

**Production:** PgBouncer in transaction mode
```yaml
# k8s/base/pgbouncer.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: pgbouncer-config
data:
  pgbouncer.ini: |
    [databases]
    agent_memory = host=postgres.supabase.co port=5432 dbname=agent_memory

    [pgbouncer]
    pool_mode = transaction
    max_client_conn = 1000
    default_pool_size = 25
    server_lifetime = 3600
    server_idle_timeout = 600
```

**Connection strings:**
- Laravel: `postgres://laravel_app@pgbouncer:6432/agent_memory`
- Python: `postgres://trading_app@pgbouncer:6432/agent_memory`

### Backup & Disaster Recovery

- **Daily automated backups:** PostgreSQL WAL archiving to S3
- **Point-in-time recovery:** Restore to any second in last 30 days
- **Monthly restore drills:** Verify backups work by restoring to staging

---

## Section 5: Authentication & Authorization

### Hybrid Auth Strategy (Token Hashing + Optional JWT)

**Critical Revision (C1):** The original spec assumed JWT auth. The actual codebase uses SHA-256 token hashing (`amc_*` prefix) with database lookup. This section describes a **hybrid approach** to avoid breaking existing agents.

**Design Goals:**
- Maintain backward compatibility with existing `amc_*` tokens (4000+ agents in production)
- Add JWT as optional for new integrations (no DB lookup per request)
- Compromised tokens can be revoked immediately via Redis blacklist
- Gradual migration path (no breaking changes)

### Current System (Keep Running)

**Laravel `AuthenticateAgent` middleware:**
```php
// api/app/Http/Middleware/AuthenticateAgent.php
Auth::viaRequest('agent-token', function (Request $request) {
    $token = $request->bearerToken();
    if (!$token || !str_starts_with($token, 'amc_')) {
        return null;
    }
    return Agent::where('token_hash', hash('sha256', $token))
        ->where('is_active', true)
        ->first();
});
```

**Characteristics:**
- Every request hits database (SELECT from agents)
- Tokens don't expire (manual revocation only)
- Works today, all existing agents use this

### New System (Add Alongside)

**JWT issuance (optional, for new agents/users):**
```php
// api/app/Http/Controllers/Auth/JwtController.php (NEW)
use Firebase\JWT\JWT;

public function issueJwt(Agent $agent)
{
    $payload = [
        'sub' => $agent->id,
        'type' => 'agent',
        'scopes' => $agent->scopes,
        'iat' => time(),
        'exp' => time() + (15 * 60),  // 15 minutes
    ];

    $token = JWT::encode($payload, env('JWT_SECRET'), 'HS256');
    return response()->json(['token' => $token, 'expires_in' => 900]);
}
```

### Python Validation (Hybrid)

**Try JWT first (fast), fallback to token hash (compatible):**
```python
# shared/auth/validate.py
import jwt
import hashlib
from redis.asyncio import Redis
from fastapi import HTTPException

JWT_SECRET = os.getenv("JWT_SECRET")

async def validate_token(token: str, redis: Redis, db) -> dict:
    """Hybrid validator: JWT first, then legacy token hash."""

    # Try JWT validation (new tokens)
    if not token.startswith('amc_'):
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])

            # Check Redis blacklist
            user_id = payload["sub"]
            is_revoked = await redis.sismember(f"revoked_tokens:{user_id}", "*") \
                      or await redis.sismember(f"revoked_tokens:{user_id}", token)
            if is_revoked:
                raise HTTPException(401, "Token revoked")

            return payload  # Fast path, no DB hit
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Invalid token")

    # Fallback: Legacy amc_* token (DB lookup)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    agent = await db.fetch_one(
        "SELECT id, name, scopes, is_active FROM agents WHERE token_hash = $1",
        token_hash
    )

    if not agent or not agent['is_active']:
        raise HTTPException(401, "Invalid or inactive agent")

    # Cache for 5 minutes to reduce DB load
    await redis.setex(f"token_cache:{token_hash}", 300, json.dumps(dict(agent)))

    return {"sub": agent['id'], "type": "agent", "scopes": agent['scopes']}
```

**FastAPI Dependency:**
```python
async def get_current_user(
    authorization: str = Header(...),
    redis: Redis = Depends(get_redis),
    db = Depends(get_db)
) -> dict:
    token = authorization.replace("Bearer ", "")
    return await validate_token(token, redis, db)
```

### Token Refresh Flow

**Frontend:**
```typescript
// src/lib/api/client.ts
memoryClient.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401) {
      // Token expired, try to refresh
      try {
        const { data } = await memoryClient.post('/auth/refresh');
        localStorage.setItem('auth_token', data.token);

        // Retry original request
        error.config.headers.Authorization = `Bearer ${data.token}`;
        return memoryClient.request(error.config);
      } catch (refreshError) {
        // Refresh failed, redirect to login
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);
```

**Laravel Refresh Endpoint:**
```php
// api/routes/api.php
Route::post('/auth/refresh', function (Request $request) {
    $user = auth()->user();  // Validates current token

    $newToken = JWT::encode([
        'sub' => $user->id,
        'type' => 'user',
        'scopes' => $user->scopes,
        'iat' => time(),
        'exp' => time() + (15 * 60),
    ], env('JWT_SECRET'), 'HS256');

    return response()->json(['token' => $newToken, 'expires_in' => 900]);
})->middleware('auth:api');
```

### Immediate Token Revocation

**When agent is deactivated:**
```php
// api/app/Observers/AgentObserver.php
public function updated(Agent $agent)
{
    if (!$agent->is_active && $agent->wasChanged('is_active')) {
        // Publish event
        event(new AgentDeactivated($agent->id));

        // Blacklist current token in Redis
        Redis::sadd("revoked_tokens:{$agent->id}", '*');  // Wildcard: revoke all tokens
        Redis::expire("revoked_tokens:{$agent->id}", 900);  // 15min TTL (matches JWT expiry)
    }
}
```

**Python consumer adds to blacklist:**
```python
@consumer.register("agent.deactivated")
async def on_agent_deactivated(payload: dict):
    agent_id = payload["agent_id"]
    await redis.sadd(f"revoked_tokens:{agent_id}", "*")
    await redis.expire(f"revoked_tokens:{agent_id}", 900)
    logger.info(f"Agent {agent_id} tokens revoked")
```

**Result:** Deactivated agent's API calls fail within seconds (next request hits blacklist), not waiting 15 minutes for JWT to expire.

---

## Section 6: Frontend Unification

### Technology Stack

- **Framework:** React 19
- **Build Tool:** Vite 5
- **Routing:** React Router v7 (with nested layouts)
- **State Management:** TanStack Query (React Query) for server state
- **Styling:** Tailwind CSS v4
- **UI Components:** shadcn/ui (from `shared/ui/`)
- **Charts:** Recharts (trading analytics)

### Routing Structure

```typescript
// src/router.tsx
import { createBrowserRouter, Navigate } from 'react-router-dom';

export const router = createBrowserRouter([
  // Public routes
  { path: '/', element: <LandingPage /> },
  { path: '/pricing', element: <PricingPage /> },
  { path: '/commons', element: <CommonsPage /> },  // Public memory feed
  { path: '/agents/:id', element: <PublicProfilePage /> },

  // Auth routes
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },

  // Authenticated routes (protected by AuthLayout)
  {
    path: '/dashboard',
    element: <AuthLayout />,  // Checks auth, renders sidebar
    children: [
      { index: true, element: <OverviewPage /> },
      { path: 'agents', element: <AgentsPage /> },
      { path: 'memories', element: <MemoriesPage /> },
      { path: 'memories/:id', element: <MemoryDetailPage /> },
      {
        path: 'trading',
        children: [
          { index: true, element: <TradingDashboard /> },
          { path: 'positions', element: <PositionsPage /> },
          { path: 'journal', element: <JournalPage /> },
          { path: 'analytics', element: <AnalyticsPage /> },
        ],
      },
      {
        path: 'arena',
        children: [
          { index: true, element: <ArenaPage /> },
          { path: 'leaderboard', element: <LeaderboardPage /> },
          { path: 'matches/:id', element: <MatchDetailPage /> },
        ],
      },
    ],
  },
]);
```

### API Client Layer

**Dual API clients with shared auth:**
```typescript
// src/lib/api/client.ts
import axios from 'axios';

export const memoryClient = axios.create({
  baseURL: import.meta.env.VITE_MEMORY_API_URL || '/api/v1',
});

export const tradingClient = axios.create({
  baseURL: import.meta.env.VITE_TRADING_API_URL || '/trading',
});

// Add auth token to both
[memoryClient, tradingClient].forEach(client => {
  client.interceptors.request.use(config => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });
});
```

**Type-safe API methods:**
```typescript
// src/lib/api/memory.ts
import { memoryClient } from './client';
import type { Agent, Memory } from '@agent-memory/types';

export const memoryApi = {
  getAgents: () => memoryClient.get<Agent[]>('/agents').then(r => r.data),
  getAgent: (id: string) => memoryClient.get<Agent>(`/agents/${id}`).then(r => r.data),
  getMemories: (params?: { limit?: number }) =>
    memoryClient.get<Memory[]>('/memories', { params }).then(r => r.data),
  searchMemories: (query: string) =>
    memoryClient.get<Memory[]>('/memories/search', { params: { q: query } }).then(r => r.data),
  createMemory: (data: Partial<Memory>) =>
    memoryClient.post<Memory>('/memories', data).then(r => r.data),
};

// src/lib/api/trading.ts
import { tradingClient } from './client';
import type { Trade, Position, TradingStats } from '@agent-memory/types';

export const tradingApi = {
  getTrades: (params?: { status?: string; ticker?: string }) =>
    tradingClient.get<Trade[]>('/trades', { params }).then(r => r.data),
  getPositions: (paper = true) =>
    tradingClient.get<Position[]>('/positions', { params: { paper } }).then(r => r.data),
  getStats: (paper = true) =>
    tradingClient.get<TradingStats>('/stats', { params: { paper } }).then(r => r.data),
  createTrade: (data: Partial<Trade>) =>
    tradingClient.post<Trade>('/trades', data).then(r => r.data),
};
```

### Data Fetching with React Query

```typescript
// src/lib/hooks/useMemories.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { memoryApi } from '@/lib/api/memory';

export function useMemories() {
  return useQuery({
    queryKey: ['memories'],
    queryFn: () => memoryApi.getMemories(),
  });
}

export function useCreateMemory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: memoryApi.createMemory,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] });
    },
  });
}

// src/lib/hooks/useTrades.ts
import { useQuery } from '@tanstack/react-query';
import { tradingApi } from '@/lib/api/trading';

export function useTrades(filters?: { status?: string }) {
  return useQuery({
    queryKey: ['trades', filters],
    queryFn: () => tradingApi.getTrades(filters),
  });
}

export function useTradingStats(paper = true) {
  return useQuery({
    queryKey: ['trading-stats', paper],
    queryFn: () => tradingApi.getStats(paper),
    refetchInterval: 30000,  // Auto-refresh every 30s
  });
}
```

### WebSocket for Realtime Updates

```typescript
// src/lib/hooks/useWebSocket.ts
import { useEffect, useState } from 'react';

export function useWebSocket<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const ws = new WebSocket(url);

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);
    ws.onmessage = (event) => {
      const parsed = JSON.parse(event.data);
      setData(parsed);
    };

    return () => ws.close();
  }, [url]);

  return { data, isConnected };
}

// Usage: Commons feed with realtime updates
function CommonsPage() {
  const { data: memories } = useQuery(['commons'], () => memoryApi.getCommons());
  const { data: newMemory } = useWebSocket<Memory>('ws://localhost:8000/ws/commons');

  useEffect(() => {
    if (newMemory) {
      queryClient.setQueryData(['commons'], (old: Memory[]) => [newMemory, ...old]);
    }
  }, [newMemory]);

  return <MemoryFeed memories={memories} />;
}
```

### Shared Component Library

**Extract to `shared/ui/` for reuse:**
```typescript
// shared/ui/src/MemoryCard.tsx
import { Memory } from '@agent-memory/types';

export interface MemoryCardProps {
  memory: Memory;
  onShare?: (id: string) => void;
  onDelete?: (id: string) => void;
}

export function MemoryCard({ memory, onShare, onDelete }: MemoryCardProps) {
  return (
    <div className="border rounded-lg p-4 hover:shadow-md transition">
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <span className="text-sm text-gray-600">{memory.type}</span>
          <p className="mt-2 text-gray-900">{memory.value}</p>
          {memory.tags && memory.tags.length > 0 && (
            <div className="flex gap-2 mt-2">
              {memory.tags.map(tag => (
                <span key={tag} className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex gap-2">
          {onShare && (
            <button onClick={() => onShare(memory.id)} className="text-blue-600">
              Share
            </button>
          )}
          {onDelete && (
            <button onClick={() => onDelete(memory.id)} className="text-red-600">
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// shared/ui/src/TradingCard.tsx
import { Trade } from '@agent-memory/types';

export function TradingCard({ trade }: { trade: Trade }) {
  const isProfitable = trade.pnl && trade.pnl > 0;

  return (
    <div className="border rounded-lg p-4">
      <div className="flex justify-between">
        <div>
          <span className="font-bold">{trade.ticker}</span>
          <span className={`ml-2 ${trade.direction === 'long' ? 'text-green-600' : 'text-red-600'}`}>
            {trade.direction.toUpperCase()}
          </span>
        </div>
        {trade.pnl && (
          <span className={isProfitable ? 'text-green-600' : 'text-red-600'}>
            {isProfitable ? '+' : ''}{trade.pnl.toFixed(2)}
          </span>
        )}
      </div>
      <div className="text-sm text-gray-600 mt-2">
        Entry: ${trade.entry_price} × {trade.quantity} @ {new Date(trade.entry_at).toLocaleString()}
      </div>
    </div>
  );
}
```

---

## Section 7: Migration Roadmap (7-Week Timeline)

### Phase 0: Python Internal Hardening (Week 1)

**Goal:** Clean up internal architecture before integration, making dependency injection explicit.

**Machine 1 Tasks:**

1. **Migrate from pydantic-settings to explicit config.py**
   ```python
   # OLD: Global singleton from pydantic-settings
   from config import settings  # Auto-loads from .env

   # NEW: Explicit configuration object
   # trading/config.py
   class Config:
       def __init__(self):
           self.database_url = os.getenv("DATABASE_URL", "sqlite:///data.db")
           self.redis_url = os.getenv("REDIS_URL", "redis://localhost")
           # ... all other settings

   def load_config() -> Config:
       return Config()
   ```

2. **Replace global Config() singleton with dependency injection**
   ```python
   # OLD: storage/db.py
   from config import settings

   class TradeStore:
       def __init__(self):
           self.db = asyncpg.connect(settings.database_url)

   # NEW: storage/db.py
   class TradeStore:
       def __init__(self, db: asyncpg.Connection):
           self.db = db

   # Usage:
   db = await asyncpg.connect(config.database_url)
   trade_store = TradeStore(db)
   ```

3. **Standardize all constructor signatures to accept db parameter**
   - Update `storage/stores.py`: `TradeStore(db)`, `PositionStore(db)`, `StatsStore(db)`
   - Update `agents/runner.py`: `AgentRunner(config, db, redis)`
   - Update `api/routes.py`: Use FastAPI dependencies for `db`

4. **Update import statements across codebase**
   - Remove `from config import settings`
   - Add `config: Config = Depends(get_config)` to route handlers
   - Pass `config` to all constructors

**Acceptance Criteria:**
- ✅ No global `settings` object anywhere in Python codebase
- ✅ All classes accept dependencies via constructor
- ✅ All tests pass with new architecture
- ✅ No change to external API contracts

---

### Phase 1: Foundation (Weeks 1-2)

**Goal:** Set up monorepo, prove tooling works, no production changes yet. Overlaps with Phase 0 (Python hardening runs in parallel with monorepo setup).

**Machine 1 Tasks:**
1. **Create monorepo structure**
   ```bash
   mkdir agent-memory-unified && cd agent-memory-unified
   git init
   cp -r ~/agent-memory/ ./api/
   cp -r ~/stock-trading-api/python/ ./trading/
   git add . && git commit -m "Initial monorepo structure"
   ```

2. **Setup shared dependencies**
   ```toml
   # pyproject.toml (root)
   [tool.uv.workspace]
   members = ["trading", "shared/types-py", "shared/events-py"]

   # trading/pyproject.toml
   [project]
   dependencies = [
     "shared-types @ {path = '../shared/types-py', editable = true}",
     "shared-events @ {path = '../shared/events-py', editable = true}",
   ]
   ```

   ```json
   // api/composer.json
   {
     "repositories": [
       {"type": "path", "url": "../shared/types-php"},
       {"type": "path", "url": "../shared/events-php"}
     ],
     "require": {
       "agent-memory/shared-types": "@dev",
       "agent-memory/shared-events": "@dev"
     }
   }
   ```

3. **Create JSON Schemas**
   - Write `agent.schema.json`, `memory.schema.json`, `trade.schema.json`
   - Run `scripts/sync-types.sh`, verify generation works
   - Import in Python: `from shared_types import Agent`
   - Import in PHP: `use AgentMemory\SharedTypes\Agent;`
   - Import in TS: `import { Agent } from '@agent-memory/types';`

4. **Setup pre-commit hooks**
   ```bash
   # .git/hooks/pre-commit
   #!/bin/bash
   ./scripts/sync-types.sh
   git add shared/types/generated/
   ```

**Acceptance Criteria:**
- ✅ All three services compile with shared types
- ✅ Changing a schema regenerates code automatically
- ✅ CI checks that generated types are committed

---

### Phase 2: Database Consolidation (Weeks 2-4)

**Goal:** Consolidate to single PostgreSQL instance, Laravel owns all migrations. Migrate all 30+ Python tables from SQLite.

**Machine 1 Tasks:**

1. **Provision unified PostgreSQL (Supabase)**
   - Create new Supabase project
   - Create DB users:
     ```sql
     CREATE USER laravel_app WITH PASSWORD '...';
     CREATE USER trading_app WITH PASSWORD '...';

     GRANT ALL ON SCHEMA public TO laravel_app;
     GRANT SELECT ON agents, users, memories TO trading_app;
     GRANT ALL ON trades, positions, trading_stats TO trading_app;
     GRANT SELECT ON trades, trading_stats TO laravel_app;
     ```

2. **Migrate agent-memory to new DB**
   ```bash
   cd api
   cp .env.example .env
   # Update: DB_HOST=new-supabase-url
   php artisan migrate  # Create schema
   ```

3. **Copy production data**
   ```bash
   # Dump old DB
   pg_dump $OLD_REMEMBR_URL > backup.sql
   # Restore to new DB
   psql $NEW_DB_URL < backup.sql
   # Verify
   php artisan tinker
   >>> Agent::count()  # Should match old count
   ```

4. **Create Python tables via Laravel migration**
   ```bash
   php artisan make:migration create_trading_tables
   ```

   (Write migration as shown in Section 4)

   ```bash
   php artisan migrate
   ```

5. **Update Python to use PostgreSQL**
   ```python
   # trading/config.py
   database_url: str = "postgresql://trading_app:pass@supabase.co/agent_memory"

   # trading/storage/db.py - Remove SQLite, use asyncpg
   import asyncpg

   async def get_connection():
       return await asyncpg.connect(settings.database_url)
   ```

6. **Migrate Python's SQLite data (all 30+ tables)**
   ```python
   # scripts/migrate-trading-data.py
   import asyncio
   import aiosqlite
   import asyncpg

   async def migrate():
       sqlite = await aiosqlite.connect('trading/data.db')
       pg = await asyncpg.connect(settings.database_url)

       # CRITICAL (C3): tracked_positions schema != new trades schema
       # Explicit column mapping required:
       async with sqlite.execute("SELECT * FROM tracked_positions") as cursor:
           async for row in cursor:
               # Map old columns to new schema
               agent_id = await lookup_agent_id(row['agent_name'])  # TEXT → UUID
               await pg.execute(
                   """INSERT INTO trades (
                       id, agent_id, ticker, direction, entry_price, quantity,
                       entry_at, status, paper, metadata
                   ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                   str(uuid.uuid4()),  # New UUID
                   agent_id,
                   row['symbol'],  # symbol → ticker
                   row['side'],  # side → direction
                   Decimal(row['entry_price']),  # TEXT → DECIMAL
                   Decimal(row['quantity']),  # TEXT → DECIMAL
                   datetime.fromisoformat(row['entry_at']),
                   'open' if not row.get('exit_at') else 'closed',
                   True,  # Assume paper for old data
                   json.dumps({"migrated_from": "tracked_positions"})
               )

       # Migrate all other tables (positions, trading_stats, opportunities, etc.)
       # See full list in Section 1 architecture diagram

       await sqlite.close()
       await pg.close()

   asyncio.run(migrate())
   ```

**Acceptance Criteria:**
- ✅ Both services read/write PostgreSQL successfully
- ✅ All production data from 30+ Python tables migrated with zero loss
- ✅ Schema mapping verified (tracked_positions → trades column alignment)
- ✅ Laravel migrations create all Python tables correctly

---

### Phase 3: Redis Streams Event Bus ✅ COMPLETE

**Status:** Already implemented in stock-trading-api (as of 2026-04-02). Ready for integration.

**Goal:** Services communicate via reliable event bus.

**Machine 1 Tasks:**

1. **Deploy Redis with persistence**
   ```yaml
   # docker-compose.yml
   redis:
     image: redis:7-alpine
     command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
     ports:
       - "6379:6379"
     volumes:
       - redis-data:/data
   ```

2. **Implement PHP Publisher**
   - Write `shared/events/EventPublisher.php` (as shown in Section 3)
   - Add to Laravel service container:
     ```php
     // api/app/Providers/AppServiceProvider.php
     $this->app->singleton(EventPublisher::class, function () {
         return new EventPublisher(Redis::connection()->client());
     });
     ```

3. **Implement Python Consumer**
   - Write `shared/events/consumer.py` (as shown in Section 3)
   - Register handlers in `trading/api/events.py`
   - Start consumer in FastAPI lifespan:
     ```python
     @asynccontextmanager
     async def lifespan(app: FastAPI):
         # Start event consumer
         asyncio.create_task(consumer.start())
         yield
     ```

4. **Publish events from Laravel**
   ```php
   // api/app/Observers/TradeObserver.php
   public function created(Trade $trade) {
       $publisher = app(EventPublisher::class);
       $publisher->publish('trade.opened', [
           'trade_id' => $trade->id,
           'agent_id' => $trade->agent_id,
           // ...
       ]);
   }
   ```

5. **Consume events in Python**
   ```python
   @consumer.register("trade.closed")
   async def on_trade_closed(payload):
       # Update local journal index
       await journal_indexer.update(payload["trade_id"])
   ```

6. **Deploy DLQ monitor**
   ```python
   # scripts/monitor-dlq.py
   async def check_dlq():
       count = await redis.xlen("events:dlq")
       if count > 100:
           await alert_ops(f"DLQ has {count} failed events")
   ```

**Acceptance Criteria:**
- ✅ Events flow Laravel → Python and Python → Laravel
- ✅ Failed events move to DLQ after 3 retries
- ✅ No Redis OOM (MAXLEN caps stream length)
- ✅ Grafana dashboard shows event lag < 1 second

---

### Phase 4: Hybrid Auth Implementation (Weeks 4-5)

**Goal:** Unified auth, immediate token revocation.

**Machine 1 Tasks:**

1. **Shorten JWT expiry**
   ```php
   // api/app/Http/Controllers/Auth/LoginController.php
   'exp' => time() + (15 * 60),  // 15 minutes, not 24 hours
   ```

2. **Add refresh endpoint**
   ```php
   Route::post('/auth/refresh', function (Request $request) {
       $user = auth()->user();
       return response()->json([
           'token' => generateJWT($user),
           'expires_in' => 900
       ]);
   })->middleware('auth:api');
   ```

3. **Implement Python JWT validation**
   - Write `shared/auth/validate.py` (as shown in Section 5)
   - Use in FastAPI:
     ```python
     @router.get("/trades", dependencies=[Depends(get_current_user)])
     async def get_trades(user: dict = Depends(get_current_user)):
         return await trade_store.find_by_agent(user["sub"])
     ```

4. **Add Redis blacklist on deactivation**
   ```php
   // api/app/Observers/AgentObserver.php
   public function updated(Agent $agent) {
       if (!$agent->is_active && $agent->wasChanged('is_active')) {
           Redis::sadd("revoked_tokens:{$agent->id}", '*');
           Redis::expire("revoked_tokens:{$agent->id}", 900);
           event(new AgentDeactivated($agent->id));
       }
   }
   ```

5. **Consume deactivation event in Python**
   ```python
   @consumer.register("agent.deactivated")
   async def on_agent_deactivated(payload):
       agent_id = payload["agent_id"]
       await redis.sadd(f"revoked_tokens:{agent_id}", "*")
       await redis.expire(f"revoked_tokens:{agent_id}", 900)
   ```

**Acceptance Criteria:**
- ✅ Python validates JWTs without calling Laravel
- ✅ Deactivated agent's requests fail within 2 seconds
- ✅ Tokens refresh seamlessly in frontend

---

### Phase 5: Frontend Unification (Weeks 5-7, **Machine 2 Parallel**)

**Goal:** Unified React SPA with feature parity. Extended to 3 weeks to account for comprehensive migration and testing (H7).

**Machine 2 Tasks:**

1. **Scaffold React app**
   ```bash
   cd frontend
   npm create vite@latest . -- --template react-ts
   npm install react-router-dom @tanstack/react-query axios
   npm install -D tailwindcss postcss autoprefixer
   npx tailwindcss init -p
   ```

2. **Setup routing**
   - Create `src/router.tsx` (as shown in Section 6)
   - Add routes for landing, auth, dashboard, trading, arena

3. **Build API clients**
   - Create `src/lib/api/memory.ts` and `trading.ts`
   - Add auth interceptors
   - Type-safe methods using `@agent-memory/types`

4. **Implement shared components**
   - Extract `MemoryCard`, `TradeCard`, `StatsWidget` to `shared/ui/`
   - Publish as `@agent-memory/ui` package
   - Import in frontend: `import { MemoryCard } from '@agent-memory/ui';`

5. **Port Vue pages to React**
   - Landing page
   - Dashboard (overview, agents list)
   - Memories feed and search
   - Arena/leaderboard

6. **Port existing React trading pages**
   - Most are copy-paste from `stock-trading-api/frontend/`
   - Update API client imports

7. **Add WebSocket for realtime**
   - Implement `useWebSocket` hook
   - Connect to commons feed SSE

**Acceptance Criteria:**
- ✅ All pages from old frontends replicated
- ✅ E2E tests pass (Playwright)
- ✅ Mobile responsive
- ✅ Lighthouse score > 90

---

### Phase 6: Integration Testing & Deployment (Week 7)

**Goal:** Zero-downtime cutover to unified stack.

**Both Machines:**

1. **Write E2E tests**
   ```typescript
   // tests/e2e/full-flow.spec.ts
   import { test, expect } from '@playwright/test';

   test('complete trading flow', async ({ page }) => {
     // Login
     await page.goto('/login');
     await page.fill('[name=email]', 'test@example.com');
     await page.fill('[name=password]', 'password');
     await page.click('button[type=submit]');

     // Open trade
     await page.goto('/dashboard/trading');
     await page.click('text=New Trade');
     await page.fill('[name=ticker]', 'AAPL');
     await page.selectOption('[name=direction]', 'long');
     await page.fill('[name=quantity]', '100');
     await page.click('text=Submit');

     // Verify trade appears
     await expect(page.locator('text=AAPL')).toBeVisible();

     // Close trade
     await page.click('text=Close Position');
     await page.fill('[name=exit_price]', '190');
     await page.click('text=Confirm');

     // Wait for event propagation
     await page.waitForTimeout(2000);

     // Verify leaderboard updated
     await page.goto('/arena/leaderboard');
     await expect(page.locator('text=test@example.com')).toBeVisible();
   });
   ```

2. **Deploy to staging**
   ```bash
   # Build images
   docker build -t agent-memory-api:staging ./api
   docker build -t agent-memory-trading:staging ./trading
   docker build -t agent-memory-frontend:staging ./frontend

   # Deploy to k8s staging namespace
   kubectl apply -f k8s/overlays/staging/
   ```

3. **Run smoke tests on staging**
   ```bash
   npm run test:e2e -- --base-url https://staging.remembr.dev
   ```

4. **Gradual production cutover**
   - **Day 1:** Deploy new PostgreSQL, point old Laravel to it
   - **Day 2:** Deploy new Laravel API, 10% of traffic via A/B test
   - **Day 3:** Deploy FastAPI trading engine, validate cross-service reads
   - **Day 4:** Deploy React frontend to `/app` subdomain
   - **Day 5:** Shift 50% traffic to new frontend
   - **Day 6:** Monitor error rates, shift 100% traffic
   - **Day 7:** Keep old Vue app at `/legacy` for 1 week fallback

5. **Rollback plan**
   - Keep old deployments running in parallel
   - DNS switch to roll back instantly
   - Database backups every hour during cutover

**Acceptance Criteria:**
- ✅ All E2E tests pass on staging
- ✅ Production cutover with <5 minutes downtime
- ✅ No data loss during migration
- ✅ Error rate < 0.1% post-deploy

---

### Post-Launch (Week 8+)

**Cleanup:**
- Delete old Vue frontend code
- Remove old stock-trading-api repo (archive on GitHub)
- Update documentation and runbooks
- Celebrate 🎉

**Next Iteration (Optional):**
- Extract LLM service to shared microservice
- Add OpenTelemetry distributed tracing
- Implement feature flags via LaunchDarkly

---

## Success Criteria

**Technical:**
- ✅ Single PostgreSQL instance, both services read/write
- ✅ Redis Streams event bus with DLQ, no lost events
- ✅ Shared types prevent model drift
- ✅ JWT auth with blacklist, tokens revoked in <2 seconds
- ✅ React frontend talks to both APIs seamlessly
- ✅ All tests pass (280+ PHP tests, 150+ Python tests, 50+ E2E tests)

**Operational:**
- ✅ Zero data loss during migration
- ✅ <5 minutes total downtime
- ✅ Both services deploy independently
- ✅ Can rollback to old stack within 5 minutes

**Business:**
- ✅ Feature parity with old frontends
- ✅ Page load time < 2 seconds
- ✅ Mobile responsive, Lighthouse > 90
- ✅ No regression in user experience

---

## Risk Mitigation

### Risk 1: Database Migration Fails

**Mitigation:**
- Practice migration 3 times on staging
- Take full backup before starting
- Keep old DB running in read-only mode during cutover
- Test rollback procedure

### Risk 2: Redis Runs Out of Memory

**Mitigation:**
- MAXLEN ~ 100000 caps stream length
- Monitor with Grafana, alert at 80% memory
- Persist to disk with AOF (appendonly yes)

### Risk 3: Event Processing Lag

**Mitigation:**
- Multiple consumer workers (scale horizontally)
- Monitor PEL (Pending Entries List), alert if lag > 100 messages
- DLQ prevents poison pills from halting system

### Risk 4: JWT Blacklist Miss

**Mitigation:**
- Short JWT expiry (15 minutes) limits blast radius
- Redis persistence ensures blacklist survives restarts
- Publish `agent.deactivated` event for redundancy

### Risk 5: Frontend Rebuild Takes Longer Than Expected

**Mitigation:**
- Machine 2 works in parallel, doesn't block backend work
- Can launch backend first, keep old frontends temporarily
- Gradual rollout (10% → 50% → 100%) catches issues early

---

## Appendix A: Environment Variables

**Unified `.env.example`:**
```bash
# App
APP_NAME="Agent Memory"
APP_ENV=production
APP_URL=https://remembr.dev

# Database (Unified PostgreSQL)
DB_CONNECTION=pgsql
DB_HOST=db.supabase.co
DB_PORT=5432
DB_DATABASE=agent_memory
DB_USERNAME=laravel_app  # or trading_app for Python
DB_PASSWORD=secret

# Redis (Event Bus + Cache)
REDIS_HOST=redis.supabase.co
REDIS_PORT=6379
REDIS_PASSWORD=secret

# JWT Auth (Shared Secret)
JWT_SECRET=your-256-bit-secret

# AI Services
GEMINI_API_KEY=...
AWS_BEDROCK_REGION=us-east-1
AWS_BEDROCK_MODEL=anthropic.claude-sonnet-4-20250514-v1:0

# Python-specific (Trading)
ANTHROPIC_API_KEY=...
GROQ_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434

# IBKR
IB_HOST=127.0.0.1
IB_PORT=4002  # Paper trading
IB_CLIENT_ID=1

# Kalshi
KALSHI_KEY_ID=...
KALSHI_PRIVATE_KEY_PATH=.keys/kalshi.pem
KALSHI_DEMO=true

# Observability
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
SENTRY_DSN=...
```

---

## Appendix B: CI/CD Pipeline

**GitHub Actions Workflow:**
```yaml
# .github/workflows/monorepo-ci.yml
name: Monorepo CI

on: [push, pull_request]

jobs:
  check-types:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Generate types
        run: ./scripts/sync-types.sh
      - name: Check uncommitted changes
        run: |
          if [[ -n $(git status --porcelain shared/types/generated/) ]]; then
            echo "Generated types not committed!"
            exit 1
          fi

  api-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: shivammathur/setup-php@v2
        with:
          php-version: 8.3
      - name: Install dependencies
        run: cd api && composer install
      - name: Run tests
        run: cd api && php artisan test

  trading-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: 3.12
      - name: Install uv
        run: pip install uv
      - name: Install dependencies
        run: cd trading && uv sync
      - name: Run tests
        run: cd trading && pytest

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 20
      - name: Install dependencies
        run: cd frontend && npm ci
      - name: Run tests
        run: cd frontend && npm test
      - name: Build
        run: cd frontend && npm run build

  e2e-tests:
    runs-on: ubuntu-latest
    needs: [api-tests, trading-tests, frontend-tests]
    steps:
      - uses: actions/checkout@v3
      - name: Start services
        run: docker-compose up -d
      - name: Wait for healthy
        run: ./scripts/wait-for-health.sh
      - name: Run E2E tests
        run: npx playwright test
```

---

**End of Specification**
