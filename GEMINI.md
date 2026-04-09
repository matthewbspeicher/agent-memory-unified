# Handoff: Agent Memory Commons (Unified Monorepo)

> **For:** Gemini AI
> **Date:** 2026-04-05
> **Status:** Unification COMPLETE (Phases 1, 2, 3, 5, 6 COMPLETE)

---

## What This Is

**Agent Memory Commons** — A unified platform combining:
1. **Trading Bot** (Python/FastAPI) — multi-agent autonomous trading system
2. **Frontend** (React) — unified dashboard for the system
(Note: Laravel API was deprecated and removed. All functions are handled by the FastAPI Trading engine)

**Monorepo structure** — shared types, unified PostgreSQL database, Redis Streams event bus

---

## Stack

| Component | Technology |
|-----------|------------|
| **Trading** | Python 3.14, FastAPI, asyncpg, PostgreSQL + pgvector |
| **Frontend** | React 19, React Router v7, TanStack Query, Vite |
| **Database** | PostgreSQL 16 (single shared database: `agent_memory`) |
| **Event Bus** | Redis Streams |
| **Types** | JSON Schema → Python (Pydantic) + TypeScript |

---

## Project Structure

```
agent-memory-unified/
├── trading/                # Python trading bot (FastAPI)
├── frontend/               # React 19 SPA
│   ├── src/                # All core pages and components
│   ├── tests/e2e/          # Playwright tests
│   ├── package.json        # Unified dependencies
│   └── playwright.config.ts
├── shared/                 # Cross-service shared code
├── nginx.conf              # Unified routing gateway
└── staging.docker-compose.yml
```

---

## Unification Progress

### ✅ Phase 1: Monorepo Foundation (100% COMPLETE)
### ✅ Phase 2: Database Consolidation (100% COMPLETE)
### ✅ Phase 3: Redis Streams Event Bus (100% COMPLETE)
- Verified: End-to-end event flow (Laravel -> Redis -> Python)

### ✅ Phase 5: Frontend Unification (100% COMPLETE)
- Ported all Vue components to React 19
- Integrated 3D Knowledge Graph
- Unified Design System (Neural Mesh)

### ✅ Phase 6: Production Cutover (100% COMPLETE)
- Playwright E2E tests implemented (`tests/e2e/`)
- Staging environment configured (`staging.docker-compose.yml`)
- Nginx reverse proxy gateway configured (`nginx.conf`)
- Production Readiness Guide created (`PROD-READY.md`)

---

## Running the Stack (Staging)

```bash
cd frontend && npm install && npm run build
docker-compose -f staging.docker-compose.yml up -d
```
Access at `http://localhost`.

---

## Final Summary

The unification of Agent Memory and Trading Bot into a single monorepo is complete. 
- **Shared Data:** All services use the same PostgreSQL database.
- **Shared Events:** Real-time communication via Redis Streams.
- **Shared Experience:** Unified React dashboard for agents, memories, and trades.
- **Verified:** E2E tests cover core user and agent flows.

**Project Status: PRODUCTION READY**
