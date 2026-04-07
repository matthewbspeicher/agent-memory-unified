# TP-013: Laravel API Decision

**Date:** 2026-04-07
**Decision:** Deprecate Laravel API; migrate essential unique features to FastAPI trading engine over time.

---

## Current State Assessment

The Laravel API (`api/`) is **not running** in production or development. All active functionality is served by the FastAPI trading engine (`trading/`). The Laravel codebase is extensive (~33 controllers, ~27 models, ~12 services) but appears to be a legacy artifact from the original product vision.

### Dependencies
- **PHP 8.2+**, Laravel 12, Octane (FrankenPHP)
- **pgvector/pgvector** 0.2.2 — vector search for memories
- **AWS Bedrock** — embeddings via Titan + Gemini fallback
- **Redis** (Predis) — event bus, caching
- **Stripe** (Laravel Cashier) — billing (not currently active)
- Dependencies are reasonably current (Laravel 12, PHP 8.2+, up-to-date packages)

---

## Feature Inventory

### Unique to Laravel (NOT in Trading Engine)

| Feature | Controllers/Services | Value | Migration Effort |
|---------|---------------------|-------|-----------------|
| **Vector Memory CRUD** | MemoryController, MemorySearchController, MemoryService, EmbeddingService | High — core product vision | M (2-3 days) |
| **Knowledge Graph** | GraphController | Medium — agent relationship visualization | S (1 day) |
| **Agent Registration & Profiles** | AgentController (register, directory, self-service) | Medium — multi-agent identity | S (1 day) |
| **Memory Sharing** | MemorySharingController | Low — cross-agent memory sharing | S (0.5 day) |
| **Workspaces** | WorkspaceController, PresenceController, SubscriptionController, MentionController, TaskController | Medium — multi-agent collaboration | L (3-5 days) |
| **Arena/Competition** | ArenaProfileController, ArenaGymController, ArenaChallengeController, ArenaMatchController | Low — agent competition system | L (3-5 days) |
| **Achievements/Badges** | AchievementController, BadgeController | Low — gamification | S (0.5 day) |
| **Session Extraction** | SessionController | Low — extract memories from sessions | S (0.5 day) |
| **Webhooks** | WebhookController | Low — event delivery to external systems | S (1 day) |
| **JWT Auth** | JwtController, AuthenticateAgent middleware | Medium — agent authentication | S (1 day) |
| **Commons (Public Memory Stream)** | CommonsPollController | Low — SSE stream (disabled due to issues) | S (0.5 day) |

### Overlapping with Trading Engine

| Feature | Laravel | Trading Engine |
|---------|---------|---------------|
| **Trading CRUD** | TradingController, TradingPositionController | Full trading routes with IBKR integration |
| **Trading Stats** | TradingStatsController | strategy_analytics, analytics routes |
| **Risk Management** | RiskController | risk routes |
| **Leaderboards** | TradingLeaderboardController, LeaderboardApiController | leaderboard routes, tournament routes |
| **Portfolio** | PortfolioController | portfolio routes |
| **Trading Signals** | SignalController | signal_features routes |
| **Trade Alerts** | TradeAlertController | Part of agent framework |
| **Trade Export** | TradeExportController | Part of analytics |
| **Replay/Simulation** | ReplayController | backtest routes |
| **Platform Stats** | StatsController | health routes |
| **Agent Management** | AgentController (basic) | agents routes (full lifecycle: start/stop/scan/evolve) |
| **Memory** | Full CRUD + vector search | Basic memory routes (search, list) |

---

## Analysis

### Why Deprecate

1. **Not running.** The Laravel API is not deployed or used. All traffic goes to FastAPI.
2. **Massive overlap.** Trading features (trades, positions, stats, risk, portfolio, leaderboards, signals, alerts, export, replay) are fully duplicated — and the FastAPI versions are the ones actually connected to the broker and data feeds.
3. **Operational burden.** Running two API servers (PHP + Python) doubles infrastructure, deployment, and monitoring complexity for a small team.
4. **Agent management diverged.** The trading engine has a sophisticated agent runner (start/stop/scan/evolve) that far exceeds the Laravel agent CRUD.
5. **Memory overlap growing.** Trading engine already has `trading/api/routes/memory.py` with search and listing capabilities, suggesting migration has already begun.

### What's Worth Preserving

1. **Vector Memory CRUD with embeddings** — This is the original product vision. The EmbeddingService (Bedrock/Gemini), MemorySearchService (pgvector cosine similarity), and Memory model represent significant business logic.
2. **Agent authentication pattern** — JWT + agent token auth is well-designed and could inform trading engine auth improvements.
3. **Database schema** — The Laravel migrations define the canonical schema (44 tables). This is already shared via `scripts/init-trading-tables.sql`.

### What's NOT Worth Preserving

1. **Arena/Competition system** — Unused, complex, no current users.
2. **Workspaces/Presence/Mentions/Tasks** — Multi-agent collaboration features with no adoption.
3. **Achievements/Badges** — Gamification with no users.
4. **Billing (Cashier)** — Not active.
5. **Trading routes** — Fully superseded by FastAPI.

---

## Recommended Path: Phased Deprecation

### Phase 1: Immediate (No Code Changes)
- Mark `api/` as deprecated in documentation
- Do NOT delete any code (preserves reference for migration)
- Continue using `scripts/init-trading-tables.sql` for schema

### Phase 2: Migrate Vector Memory (When Needed)
- Port `EmbeddingService` logic to Python (Bedrock/Gemini embedding calls)
- Port `MemorySearchService` pgvector queries to SQLAlchemy/asyncpg
- Add full Memory CRUD endpoints to trading engine's `memory.py` routes
- Estimated effort: 2-3 days

### Phase 3: Clean Up (After Migration)
- Remove `api/` from docker-compose and deployment configs
- Archive `api/` directory (or move to a separate branch)
- Update CLAUDE.md architecture diagram

### What NOT to Migrate
- Arena, Workspaces, Presence, Mentions, Tasks, Achievements, Badges
- These can be rebuilt from scratch IF product direction requires them

---

## Decision Summary

**Deprecate the Laravel API.** The trading engine (FastAPI) is the active, running system. The only unique high-value feature is vector memory with embeddings, which should be migrated to FastAPI when the product needs it. All other unique Laravel features (arena, workspaces, achievements) have no users and should not be migrated proactively.
