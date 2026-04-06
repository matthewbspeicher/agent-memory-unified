# Handoff: Agent Memory Commons (Unified Monorepo)

> **For:** Gemini AI
> **Date:** 2026-04-05
> **Status:** Unification in progress (Phase 2 complete, Phase 3 30%, Phase 5 10%)

---

## What This Is

**Agent Memory Commons** — A unified platform combining:
1. **Memory API** (Laravel) — persistent shared memory for AI agents
2. **Trading Bot** (Python/FastAPI) — multi-agent autonomous trading system
3. **Frontend** (React) — unified dashboard for both systems

**Monorepo structure** — shared types, unified PostgreSQL database, Redis Streams event bus

---

## Stack

| Component | Technology |
|-----------|------------|
| **API** | Laravel 12, PHP 8.3, PostgreSQL + pgvector |
| **Trading** | Python 3.14, FastAPI, asyncpg |
| **Frontend** | React 19, React Router v7, TanStack Query, Vite |
| **Database** | PostgreSQL 16 (single shared database: `agent_memory`) |
| **Event Bus** | Redis Streams (replacing Pub/Sub) |
| **Types** | JSON Schema → Python (Pydantic) + PHP + TypeScript |

---

## Project Structure

```
agent-memory-unified/
├── api/                    # Laravel 12 API (memory commons)
│   ├── app/
│   │   ├── Models/         # Agent, Memory, Arena*
│   │   ├── Services/       # EmbeddingService, MemoryService
│   │   └── Http/
│   │       ├── Controllers/Api/  # Memory, Agent, Arena endpoints
│   │       └── Middleware/       # AuthenticateAgent (bearer tokens)
│   ├── database/migrations/      # 30+ migrations (including trading tables)
│   ├── routes/api.php      # All /v1 routes
│   └── tests/Feature/      # 198 Pest tests
│
├── trading/                # Python trading bot (FastAPI)
│   ├── api/
│   │   └── app.py          # FastAPI app (trades, orders endpoints)
│   ├── agents/             # Trading agent implementations
│   ├── brokers/            # Broker integrations (Alpaca, IB)
│   ├── storage/
│   │   ├── db.py           # DatabaseConnection (asyncpg)
│   │   └── migrations.py   # DEPRECATED (Laravel owns DDL now)
│   └── events/
│       ├── consumer.py     # OLD Pub/Sub (to be removed)
│       └── consumer_streams.py  # NEW Redis Streams consumer
│
├── frontend/               # React 19 SPA (in progress)
│   ├── src/
│   │   ├── pages/          # Login, Dashboard, MemoryList, TradeHistory
│   │   ├── components/     # (empty - to be created)
│   │   └── lib/            # (empty - API client to be created)
│   ├── package.json        # React 19, React Router v7, TanStack Query
│   └── vite.config.ts      # Proxy /api → localhost:8000
│
├── shared/                 # Cross-service shared code
│   ├── types/
│   │   ├── schemas/        # JSON Schemas (source of truth)
│   │   └── generated/      # Python, PHP, TypeScript types
│   └── events-php/
│       └── src/EventPublisher.php  # Redis Streams publisher
│
└── docs/superpowers/plans/ # Implementation plans (6 phases)
```

---

## Unification Progress

### ✅ Phase 1: Monorepo Foundation (100% COMPLETE)
- Shared types directory with JSON Schemas
- Type generation working (Python, PHP, TypeScript)
- Python workspace configured (pyproject.toml)
- PHP Composer path repositories
- Pre-commit hook for type regeneration
- **Status:** All committed, 10 tests passing

### ✅ Phase 2: Database Consolidation (100% COMPLETE)
- Python converted from SQLite to PostgreSQL
- Laravel owns all DDL via migrations
- 83 tables in shared database (`agent_memory`)
- Python's `run_migrations()` disabled
- Verified: Python can read/write to Postgres
- **Status:** Committed, tested working

### ⚠️ Phase 3: Redis Streams Event Bus (30% COMPLETE)
**Done:**
- `EventPublisher.php` created (PHP side, XADD with MAXLEN)
- `consumer_streams.py` created (Python side, consumer groups + DLQ)
- Committed

**TODO:**
- Wire EventPublisher into Laravel (Trade model observers)
- Start StreamsConsumer in FastAPI app.py
- Remove old consumer.py
- Test end-to-end event flow
- **Estimated:** 2 hours

### ❌ Phase 4: ???
- No plan exists (skipped or missing)

### ⚠️ Phase 5: Frontend Unification (10% COMPLETE)
**Done:**
- Basic scaffold (package.json, vite.config.ts, tailwind, tsconfig)
- 6 source files (App.tsx, main.tsx, 4 placeholder pages)

**TODO:**
- API client (3 files: client.ts, memory.ts, trading.ts)
- Routing setup (router.tsx)
- 14 components (MemoryCard, TradeList, AgentProfile, etc.)
- nginx reverse proxy config
- **Estimated:** 8-10 hours

### ❌ Phase 6: Production Cutover (0% COMPLETE)
- E2E tests (Playwright)
- Staging deployment
- Production cutover
- **Estimated:** 4 hours

---

## Running the Stack

### 1. Start Infrastructure

```bash
# PostgreSQL (via Docker)
docker-compose up -d postgres

# Redis (local)
redis-server  # or: brew services start redis
```

### 2. Start Laravel API

```bash
cd api
composer install
cp .env.example .env  # fill in DB creds
php artisan migrate
php artisan serve  # → http://localhost:8000

# Test
php artisan test
```

**Key env vars:**
- `DB_CONNECTION=pgsql`
- `DB_DATABASE=agent_memory`
- `REDIS_HOST=127.0.0.1`
- `GEMINI_API_KEY=...` (for embeddings)

### 3. Start Python Trading Bot

```bash
cd trading
pip install -e .  # or: uv pip install -e .
cp .env.example .env  # fill in DATABASE_URL

# Run FastAPI
python3 -m uvicorn api.app:app --port 8080 --reload
# → http://localhost:8080
```

**Key env vars:**
- `DATABASE_URL=postgresql://postgres:secret@127.0.0.1:5432/agent_memory`
- `REDIS_URL=redis://127.0.0.1:6379`

### 4. Start React Frontend (when ready)

```bash
cd frontend
npm install
npm run dev  # → http://localhost:3000
```

---

## Database Schema

**Single shared database:** `agent_memory` (PostgreSQL 16)

**83 tables total:**
- Memory system: `agents`, `memories`, `memory_shares`, `memory_relations`, `workspaces`
- Arena: `arena_profiles`, `arena_gyms`, `arena_challenges`, `arena_sessions`, `arena_session_turns`, `arena_matches`, `arena_tournaments`
- Trading (43 tables): `opportunities`, `trades`, `tracked_positions`, `agent_registry`, `consensus_votes`, `leaderboard_cache`, `backtest_results`, `tournament_rounds`, etc.

**Migrations live in:** `api/database/migrations/`
**Python migrations DISABLED:** `trading/storage/migrations.py` is now a no-op

---

## Event Bus (Redis Streams)

**Publisher (PHP):**
```php
use AgentMemory\SharedEvents\EventPublisher;

$publisher = new EventPublisher($redis, 'events');
$publisher->publish('AgentDeactivated', ['agent_id' => 123]);
```

**Consumer (Python):**
```python
from events.consumer_streams import StreamsEventConsumer

consumer = StreamsEventConsumer(redis, stream="events", group="trading-service")
consumer.register("AgentDeactivated", handle_agent_deactivated)
await consumer.start()
```

**Event envelope:**
```json
{
  "id": "uuid",
  "type": "AgentDeactivated",
  "version": "1.0",
  "timestamp": "2026-04-05T21:00:00Z",
  "source": "api",
  "payload": { "agent_id": 123, "agent_name": "trader_1" },
  "metadata": {}
}
```

**Features:**
- Consumer groups (multiple workers)
- Dead-letter queue (DLQ)
- Automatic retries (3 max)
- MAXLEN ~ 10000 (prevents Redis OOM)

---

## Key Design Decisions

### 1. Monorepo Structure
- All services in one repo
- Shared types via JSON Schema
- Single source of truth for data models
- No code duplication across services

### 2. Database Strategy
- **Single PostgreSQL database** for all services
- Laravel owns DDL (all migrations in Laravel)
- Python uses read/write only (no schema changes)
- pgvector extension for embeddings

### 3. Event Bus
- **Redis Streams** (not Pub/Sub)
- Streams provide: persistence, consumer groups, DLQ, retries
- Pub/Sub was unreliable (messages lost on disconnect)

### 4. Type Generation
- JSON Schemas are source of truth
- Generated code for Python, PHP, TypeScript
- Pre-commit hook regenerates on schema changes
- Never manually edit generated types

### 5. Frontend
- React 19 (not Vue) for unified experience
- Single API URL, nginx routes to correct backend
- TanStack Query for data fetching
- React Router v7 for routing

---

## Testing

### Laravel (Pest)
```bash
cd api
php artisan test
# 198 tests, 648 assertions
```

### Python (pytest)
```bash
cd trading
pytest
# 10 tests (types integration)
```

### Frontend (none yet)
```bash
# TODO: Playwright E2E tests (Phase 6)
```

---

## Current Blockers & Next Steps

### No blockers - ready to proceed:

1. **Phase 3 integration (2h):**
   - Wire EventPublisher into Laravel Trade model
   - Start StreamsConsumer in FastAPI app.py
   - Test end-to-end event flow

2. **Phase 5 frontend (8-10h):**
   - Create API client (client.ts, memory.ts, trading.ts)
   - Setup routing (router.tsx)
   - Port 14 components from old Vue app
   - nginx reverse proxy config

3. **Phase 6 deployment (4h):**
   - Playwright E2E tests
   - Deploy to staging
   - Production cutover

**Total remaining:** ~15 hours of work

---

## Gotchas & Common Issues

### 1. Migration Status Mismatch
- **Symptom:** Migration exists but not marked as run
- **Fix:** Manually insert into `migrations` table (done for Phase 2)

### 2. TYPE Mismatch in Python
- **Symptom:** `asyncpg.exceptions.DatatypeMismatchError: column "created_at" is of type timestamp`
- **Cause:** Old Python migrations used TEXT, database has TIMESTAMP
- **Fix:** Use actual schema from database (check with `\d table_name`)

### 3. Redis Pub/Sub Message Loss
- **Symptom:** Events not received after disconnect
- **Fix:** Use Redis Streams (Phase 3), not Pub/Sub

### 4. Frontend Missing Dependencies
- **Symptom:** Import errors, no routing, no components
- **Status:** Expected - frontend is 10% complete
- **Fix:** Complete Phase 5 tasks

### 5. Multiple Trading Migrations
- There are 3 trading migrations (2026_04_05_000001, 000002, and 2026_04_13_000000)
- The big one (2026_04_13_000000) was auto-generated but redundant
- Tables already created by earlier migrations
- All marked as run to avoid conflicts

---

## API Endpoints

### Memory API (Laravel, port 8000)
- `POST /api/v1/agents/register` — Register new agent
- `GET /api/v1/memories` — List memories
- `POST /api/v1/memories` — Create memory
- `GET /api/v1/memories/search?q=` — Semantic search
- `GET /api/v1/commons/poll` — Public feed (polling)
- `GET /api/v1/arena/leaderboard` — Agent rankings

### Trading API (Python, port 8080)
- `GET /api/v1/trades` — List trades
- `POST /api/v1/trades` — Open trade
- `POST /api/v1/trades/{id}/close` — Close trade
- `GET /api/v1/orders` — Order history

---

## Deployment

**Current:** Local development only

**Planned (Phase 6):**
- Frontend: Railway (nginx + React static build)
- API: Railway (Laravel + FrankenPHP)
- Trading: Railway (Python + uvicorn)
- Database: Supabase PostgreSQL
- Redis: Upstash

---

## Git Workflow

```bash
# Check unification progress
git log --oneline | head -20

# Recent commits show:
# - feat(events): Phase 3 implementation
# - test(db): Phase 2 complete
# - feat(db): disable Python's run_migrations()
# - feat(types): integration tests
```

**Pre-commit hook:** Regenerates types from JSON Schemas on every commit

---

## Who to Ask

- **Original API (Laravel):** Built by Claude Opus 4.6, documented in `api/HANDOFF.md`
- **Trading Bot (Python):** Original system, being integrated
- **Unification Plan:** All in `docs/superpowers/plans/*.md` (6 phases)
- **Current Session:** Claude Sonnet 4.5 executing unification

---

## Summary

You're picking up mid-unification:
- **Phase 1 & 2:** ✅ Complete (types + database consolidated)
- **Phase 3:** 30% (event bus code written, not integrated)
- **Phase 5:** 10% (frontend scaffolded, needs components)
- **Phase 6:** 0% (testing + deployment)

**Next task:** Integrate Phase 3 event bus (wire up publishers/consumers, test end-to-end)

**Fastest path:** Continue Phase 3 → Phase 5 → Phase 6 in order. No blockers.
