# ADR-0004: Unified API Surface and Service Boundaries

**Status:** superseded by [ADR-0006](0006-laravel-removal.md)
**Date:** 2026-04-08
**Deciders:** Architecture review, 2026-04-08 session

> ⚠️ **Superseded by ADR-0006 (Laravel removal, 2026-04-09).**
> This ADR's central premise — a coexisting Laravel `/api/v1/*` Product API alongside a FastAPI `/engine/v1/*` Trading Engine — no longer holds. Laravel was removed entirely the day after this was written. The `/engine/v1/*` route prefix scheme and uv-as-single-source-of-truth dependency decisions remain in force; everything mentioning Laravel as a live system is historical context only. Preserved for the migration plan and the FastAPI route conventions.

---

## Context

The current architecture has accumulated several inconsistencies that burden frontend development and create unclear contract boundaries.

### Current Problems

1. **Route Prefix Inconsistency**
   - `competition.py` has `prefix="/api/competition"` 
   - Frontend calls `/competition/dashboard/summary`
   - Result: `/api/competition/competition/dashboard/summary` (DOUBLE prefix!)

2. **WebSocket URL Mismatch**
   - FastAPI defines `/ws/public` (prefix `/ws`)
   - Frontend uses hardcoded `/api/trading-direct/ws/public`
   - No Vite proxy exists for `/api/trading-direct/ws`

3. **Multiple Transport Instances**
   - `client.ts` → axios with `/api` base (Laravel)
   - `competition.ts` → separate axios instance
   - `bittensor.ts` → another separate axios instance
   - Frontend must know which transport to use per feature

4. **Dependency Management Fragmentation**
   - requirements.txt, requirements-test.txt, pyproject.toml all claim to own dependencies
   - No lockfile, no reproducible installs

---

## Decision

### 0. Dependency Management: uv as Single Source of Truth

**Key Change:** Deprecate `requirements.txt` and `requirements-test.txt`. Use `pyproject.toml` as the sole manifest, managed via `uv sync`.

| File | Status |
|------|--------|
| `pyproject.toml` | **Canonical manifest** - single source of truth |
| `requirements.txt` | Deprecated - auto-generated for compatibility |
| `requirements-test.txt` | Deprecated - removed |
| `uv.lock` | **Generated** - reproducible installs |

```bash
# Install all dependencies
uv sync

# Install with optional groups
uv sync --extra torch
uv sync --extra ml

# Lockfile ensures reproducible CI runs
```

### 1. Two-API Boundary

Frontend treats them as **distinct APIs**, not a faux unified boundary:

| Namespace | Owner | Purpose | Auth |
|-----------|-------|---------|------|
| `/api/v1/*` | Laravel | Product API (human actions) | JWT Bearer |
| `/engine/v1/*` | FastAPI | Trading/Agent engine | X-API-Key |

**Rationale:** Clear separation prevents coupling. Frontend knows which transport to use based on URL prefix.

### 2. Memory API: CQRS Boundary

| Layer | Owner | Responsibility |
|-------|-------|----------------|
| **Human-Facing Memory** | Laravel | UI, 3D Graph, Auth, Agent coordination |
| **Agent-Facing Memory** | FastAPI | LLM ingestion, Daily Compilers, Indexing, Semantic Search |

**Overlap to Remove:** FastAPI should not expose routes that Laravel owns (e.g., memory CRUD for human agents). FastAPI memory routes are for **machine agents** only.

### 3. Canonical Route Prefixes (FastAPI under `/engine/v1`)

| Domain | Prefix | Example |
|--------|--------|---------|
| Trading | `/engine/v1/trading` | `/engine/v1/trading/accounts` |
| Competition | `/engine/v1/competition` | `/engine/v1/competition/leaderboard` |
| Bittensor | `/engine/v1/bittensor` | `/engine/v1/bittensor/status` |
| Memory (Agent) | `/engine/v1/memory` | `/engine/v1/memory/memories` |
| WebSocket | `/engine/v1/ws` | `/engine/v1/ws/public` |
| Health | `/engine/v1/health` | `/engine/v1/health/ready` |

| Domain | Prefix | Example |
|--------|--------|---------|
| Trading (accounts, orders, positions) | `/api/trading` | `/api/trading/accounts` |
| Competition | `/api/competition` | `/api/competition/leaderboard` |
| Bittensor | `/api/bittensor` | `/api/bittensor/status` |
| Memory | `/api/memory` | `/api/memory/memories` |
| WebSocket | `/api/ws` | `/api/ws/public` |
| Health | `/api/health` | `/api/health/ready` |

**Change Required:**
- Remove `/api` prefix from individual route files
- Add centralized router registration in `app.py`
- Update Vite proxy to route `/api/{domain}` → trading service

### 4. Unified Transport Layer (Frontend)

Single axios instance per backend:

```typescript
// lib/api/trading.ts (FastAPI engine)
export const tradingApi = axios.create({
  baseURL: import.meta.env.DEV 
    ? '/engine/v1'  // Vite proxy
    : import.meta.env.VITE_TRADING_API_URL + '/engine/v1',
  headers: {
    'X-API-Key': import.meta.env.VITE_TRADING_API_KEY,
  },
});

// lib/api/client.ts (Laravel product API)
export const api = axios.create({
  baseURL: '/api/v1',  // Vite proxy → Laravel
});
```

### 5. WebSocket Endpoint

WebSocket at `/engine/v1/ws/public` (authenticated via message payload):

```typescript
const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/engine/v1/ws/public`;
```

### 6. Vite Proxy Configuration

```typescript
proxy: {
  // Laravel Product API
  '/api/v1': { 
    target: 'http://localhost:8000', 
    changeOrigin: true, 
    ws: true 
  },
  // FastAPI Trading Engine
  '/engine/v1': { 
    target: 'http://localhost:8080', 
    changeOrigin: true, 
    ws: true 
  },
}
```

### 7. Background Workers Isolation

Extract long-running background tasks into `api/startup/workers.py`:

```python
# api/startup/workers.py
class BackgroundWorkers:
    def __init__(self, app: FastAPI):
        self.app = app
        self.tasks: list[asyncio.Task] = []
    
    async def start(self):
        # DailyTradeCompiler
        self.tasks.append(asyncio.create_task(self._daily_compiler()))
        # FidelityFileWatcher  
        self.tasks.append(asyncio.create_task(self._file_watcher()))
        # BittensorScheduler
        self.tasks.append(asyncio.create_task(self._bittensor_scheduler()))
    
    async def stop(self):
        for task in self.tasks:
            task.cancel()
```

---

## Consequences

### Positive
- Two distinct namespaces prevent backend coupling
- uv lockfile ensures reproducible installs
- Background workers isolated for testability
- Memory boundary clear (CQRS)

### Negative
- Requires updating all frontend API call sites
- Breaking change for any external consumers
- Vite proxy becomes more verbose

---

## Migration Plan

### Phase 1: Dependency Management
- [x] Fix imports (dependencies.py, validate.py, learning/__init__.py)
- [x] Consolidate to pyproject.toml
- [ ] Add `uv.lock` generation
- [ ] Remove requirements.txt / requirements-test.txt references

### Phase 2: API Boundary
- [ ] Update FastAPI routes to use `/engine/v1/{domain}` prefix
- [ ] Update Vite proxy
- [ ] Create unified frontend transport layer
- [ ] Update frontend API call sites

### Phase 3: Startup Decomposition
- [ ] Extract `api/startup/` modules (config, infra, routers, workers)
- [ ] Create `api/startup/workers.py` for background tasks
- [ ] Remove dead DI indirection (deps.py, container.py)

### Phase 4: Memory Boundary
- [ ] Audit FastAPI memory routes
- [ ] Remove overlapping Laravel routes
- [ ] Document CQRS boundary

---

## References

- Original findings: `refact.txt`
- FastAPI routes: `trading/api/routes/*.py`
- Frontend API: `frontend/src/lib/api/*.ts`
- Vite config: `frontend/vite.config.ts`
