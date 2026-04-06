# Handoff: Agent Memory Commons (Unified Monorepo)

> **For:** Gemini AI
> **Date:** 2026-04-05
> **Status:** Unification in progress (Phase 3 complete, Phase 5 complete)

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
├── trading/                # Python trading bot (FastAPI)
├── frontend/               # React 19 SPA
│   ├── src/
│   │   ├── pages/          # Landing, Login, Dashboard, Memories, Arena, Commons, Leaderboard, Webhooks, Workspaces, KnowledgeGraph, AgentProfile
│   │   ├── components/     # AgentBadge, MemoryCard, TradeList, CreateMemoryForm, Layout
│   │   ├── lib/            # api/, auth.ts
│   │   └── lib/api/        # client.ts, agent.ts, memory.ts, trading.ts, arena.ts, webhook.ts, workspace.ts
│   ├── package.json
│   └── vite.config.ts
├── shared/                 # Cross-service shared code
└── docs/superpowers/plans/ # Implementation plans
```

---

## Unification Progress

### ✅ Phase 1: Monorepo Foundation (100% COMPLETE)
### ✅ Phase 2: Database Consolidation (100% COMPLETE)
### ✅ Phase 3: Redis Streams Event Bus (100% COMPLETE)
- Verified: End-to-end event flow (Laravel -> Redis -> Python)

### ❌ Phase 4: ???

### ✅ Phase 5: Frontend Unification (100% COMPLETE)
- Basic scaffold (package.json, vite.config.ts, tailwind, tsconfig)
- Global styles (Mesh Grid, Glass Panel, Neural Cards)
- Auth system (`useAuth` hook, `lib/auth.ts`)
- API Clients (Full coverage: Agent, Memory, Trading, Arena, Webhook, Workspace)
- Navigation Layout (Ported from Vue AppLayout)
- All Core Pages Ported (Landing, Leaderboard, Commons, Arena, Webhooks, Workspaces, KnowledgeGraph, AgentProfile, ArenaGym, ArenaMatch)
- Components (AgentBadge, MemoryCard, TradeList)
- 3D Knowledge Graph integration (3d-force-graph)
- nginx reverse proxy config drafted

### ❌ Phase 6: Production Cutover (0% COMPLETE)
- E2E tests (Playwright)
- Staging deployment
- Production cutover
- **Estimated:** 4 hours

---

## Summary

You're picking up mid-unification:
- **Phase 1, 2, 3, 5:** ✅ Complete
- **Phase 6:** 0% (Deployment and final testing)

**Next task:** Start Phase 6 — Production Cutover.

**Fastest path:** Implement basic Playwright E2E tests to verify the unified flow, then begin deployment setup.
