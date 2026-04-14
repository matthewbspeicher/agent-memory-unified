# Master Implementation Roadmap

**Created**: 2026-04-14
**Status**: Planning

16 recommendations organized into 4 phases with dependencies, acceptance criteria, and time estimates.

---

## Phase 0: Prerequisites (Day 1, ~2h)

### 0.1 Fix Failing Test — `test_orders_delete_correct_scope_allowed`

**Problem**: `test_route_scope_enforcement.py::test_orders_delete_correct_scope_allowed` fails with `ResponseValidationError` — the mock response returns `MagicMock` for the `status` field where a string is expected.

**Root Cause**: The test fixture creates mock app with `verify_api_key` override, but the DELETE `/api/v1/orders/{order_id}` handler (`cancel_order` in `trading/utils/audit.py:143`) hits a path where the response model expects `status: str` but the mock broker returns a MagicMock.

**Files**:
- `trading/tests/unit/test_route_scope_enforcement.py` — Fix mock setup
- Potentially `trading/utils/audit.py` — Check `cancel_order` response schema

**Steps**:
1. Read the test conftest to understand how `app_write_orders` fixture creates its app
2. In the mock, ensure `cancel_order` path returns a response with `status` as string, not MagicMock
3. Either: stub the broker mock to return `status="cancelled"`, or mock the `audit_event` + broker to produce a proper response
4. Run `cd trading && python -m pytest tests/unit/test_route_scope_enforcement.py -v --tb=short` to verify

**Acceptance**: All 2303 tests pass. `test_orders_delete_correct_scope_allowed` passes.

**Time**: 30min

---

### 0.2 Merge Unmerged Branches

**Prerequisite**: 0.1 must pass first (green CI before merge).

#### 0.2a: `feature/critical-fixes` (1 commit)

Pydantic backward compat fix. Low risk. Fast-forward merge.

```bash
git checkout main && git merge feature/critical-fixes
```

**Acceptance**: Build passes. No new test failures.

**Time**: 15min

#### 0.2b: `feature/mission-control-backend` (50+ commits)

Contains Mission Control API endpoints, signal pipeline wiring, MinerConsensusAggregator. High value but large diff — needs careful review.

**Steps**:
1. `git diff main..feature/mission-control-backend --stat` to assess scope
2. Resolve any conflicts with main (recent `fix:` commits may overlap)
3. Run full test suite after merge
4. Verify Mission Control endpoints load: `curl -H "X-API-Key: local-validator-dev" http://localhost:8080/api/v1/mission-control/status`

**Acceptance**: All tests pass. Mission Control endpoints respond. No regression in existing routes.

**Time**: 1-1.5h

---

### 0.3 Complete TP-015: Vector Memory Preflight Check

**Problem**: Step 0 (check pgvector, config, HNSW index) is incomplete. This blocks hybrid memory feature.

**Files**:
- `trading/storage/memory.py` — Add `_preflight_check()` method to LocalMemoryStore
- `trading/api/routes/memory.py` — Add `/memory/health` endpoint that runs preflight

**Steps**:
1. Add `_preflight_check()` to `LocalMemoryStore.__init__`:
   - Verify `pgvector` extension installed: `SELECT extname FROM pg_extension WHERE extname='vector'`
   - Verify `STA_MEMORY_TABLE` config exists
   - Verify HNSW index on embedding column: `SELECT indexname FROM pg_indexes WHERE tablename='memories' AND indexdef LIKE '%hnsw%'`
   - Log warnings for missing items; set `self._vector_ready = bool(all checks pass)`
2. Add `GET /memory/health` endpoint returning preflight status
3. Gate vector search on `self._vector_ready` (fall back to text search with warning)
4. Unit test with mock DB

**Acceptance**: Preflight runs on startup. `/memory/health` returns vector readiness status. Vector search degrades gracefully.

**Time**: 1h

---

## Phase 1: Quick Wins (Days 2-3, ~8h)

### 1.1 Shadow Mode Agent Promotion — 90% → 100%

**Current**: `shadow.py:promote_agent` persists to `agent_store.update()` with `shadow_mode=0` and calls `runner.update_agent_shadow_mode()`. Almost complete.

**Gap**: `runner.update_agent_shadow_mode()` may not exist as a proper method on all runner implementations.

**Files**:
- `trading/api/routes/shadow.py` — Verify promote logic (lines 106-173)
- `trading/agents/runner.py` (or equivalent) — Confirm `update_agent_shadow_mode` method
- `trading/tests/unit/test_shadow.py` — Add promote integration test

**Steps**:
1. Search for `update_agent_shadow_mode` implementation — verify it exists on the actual runner class
2. If missing, implement on agent runner: toggle `shadow_mode` flag, unsubscribe from live feed, subscribe to real execution pipeline
3. Add test: POST `/shadow/agents/{name}/promote` → 200, agent no longer in shadow mode
4. Add test: promote non-shadow agent → 400

**Acceptance**: Promote endpoint works end-to-end. Agent transitions from shadow to live. Tests pass.

**Time**: 1-2h

---

### 1.2 Achievements Multi-User Support — 80% → 100%

**Current**: `AchievementTracker` is a singleton (global state). `create_tracker()` in `achievements/__init__.py` always returns same tracker. No per-user scoping.

**Gap**: Need `agent_name` (or user) dimension for unlock tracking.

**Files**:
- `trading/achievements/tracker.py` — Add `agent_name` parameter, store per-agent unlocks
- `trading/achievements/registry.py` — No changes needed (definitions are global)
- `trading/api/routes/achievements.py` — Add `?agent_name=` query param to endpoints
- `trading/storage/db.py` — Add `agent_achievements` table or column
- `trading/tests/unit/test_achievements.py` — Add multi-agent tests

**Steps**:
1. Add `agent_name` to `AchievementTracker.__init__` and `create_tracker(agent_name=None)`
2. Store unlocks keyed by `(agent_name, achievement_id)` instead of just `achievement_id`
3. DB migration: `ALTER TABLE achievements ADD COLUMN agent_name TEXT DEFAULT '*';` (or new table)
4. Update routes: `GET /achievements?agent_name=foo`, `GET /achievements/me?agent_name=foo`
5. Backward-compat: no `agent_name` = global tracker (current behavior)

**Acceptance**: Achievements scoped per-agent. Global achievements still work. API backward-compatible.

**Time**: 2-3h

---

### 1.3 Memory Consolidation LLM Wiring — 70% → 90%

**Current**: `consolidator.py` lines 57-67 detect LLM client interface via `hasattr` duck-typing, falling back to a hardcoded string mock when interface is unknown.

**Gap**: The trading engine has a proper `LLMClient` in `trading/llm/client.py` with `generate()` and `agenerate()` methods. Needs to be wired.

**Files**:
- `trading/integrations/memory/consolidator.py` — Replace duck-typing with proper `LLMClient` injection
- `trading/api/container.py` — Wire `LLMClient` into consolidator construction
- `trading/tests/unit/test_consolidator.py` — Add tests with real `LLMClient` mock

**Steps**:
1. Import `LLMClient` from `trading/llm/client.py`
2. Change `MemoryConsolidator.__init__` to accept `llm_client: LLMClient` type hint
3. Replace lines 57-67 with: `consolidated_value = await self.llm.agenerate(prompt)` (matching LLMClient's actual method)
4. Remove the `hasattr`/`__call__` fallback branches — if LLM is unavailable, skip consolidation with a warning
5. Wire in `container.py`: pass `self.llm_client` to `MemoryConsolidator`
6. Add unit test: mock LLMClient returning a summary → consolidation event published to Redis

**Acceptance**: Consolidator uses LLMClient properly. No mock fallback. Graceful degradation when LLM unavailable.

**Time**: 1-2h

---

### 1.4 Lab Page Enhancement

**Current**: Lab page (`Lab.tsx`) works but is minimal — shows config, backtest results, equity curve, and deploy button. No validation testing, no agent comparison, no signal replay.

**Enhancement**: Add validation testing tab (signal replay, paper trading verification).

**Files**:
- `frontend/src/pages/Lab.tsx` — Add tabs: Validation, Logs
- `frontend/src/lib/api/drafts.ts` — Add polling for backtest status

**Steps**:
1. Add tabbed layout: `Backtest | Validation | Logs`
2. **Backtest tab** (current): already functional
3. **Validation tab**: Show signal log from agent's recent signals, allow replaying against historical data
4. **Logs tab**: Stream agent logs during backtest/deploy
5. Add `useEffect` polling for backtest status while `backtesting===true`
6. Add error boundary around the component

**Acceptance**: Lab page has 3 tabs. Backtest runs and shows results. Validation tab renders (even if empty state for now).

**Time**: 2-3h

---

### 1.5 Arbitrage Dual-Leg Execution — 50% → 90%

**Current**: `arbitrage.py:execute_arbitrage` claims the spread but returns `{"status": "claimed"}` without executing the dual-leg trade.

**Gap**: Need `ArbTrade` model construction, broker order submission for both legs, and fill tracking.

**Files**:
- `trading/api/routes/arbitrage.py` — Replace lines 46-57 with actual execution logic
- `trading/broker/interfaces.py` — Add `submit_arb_leg()` or use existing order submission
- `trading/storage/arb_store.py` — Track arb trade state (claimed → leg1_filled → completed)
- New: `trading/integrations/arb/executor.py` — ArbExecutor class for dual-leg coordination

**Steps**:
1. Create `ArbTrade` model: `id, observation_id, agent_name, leg1_order_id, leg2_order_id, state, pnl`
2. Create `ArbExecutor` class:
   - `async execute(claim, broker)`: submit leg1 (buy on exchange A), await fill, then submit leg2 (sell on exchange B)
   - Handle partial fills and timeout
   - On leg2 failure, attempt to close leg1 (risk management)
3. Wire `ArbExecutor` into `arbitrage.py` route via `app.state`
4. Add `ArbStore` tracking: `claimed → executing → completed/failed`
5. Unit test with mock broker: verify both legs submitted, state transitions

**Acceptance**: Dual-leg execution triggers. State tracked in ArbStore. Graceful failure handling. Tests pass.

**Time**: 4-5h

---

## Phase 2: Core Features (Days 4-7, ~25h)

### 2.1 Go-Trader Phase 1: Risk Hardening (9-12h)

Three risk features from `docs/plans/go-trader-incorporation-plan.md`:

#### 2.1a: Portfolio-Level Kill Switch (~4h)

Persists portfolio HWM and auto-triggers kill switch on 25% drawdown. Full code in plan doc.

**Files to create**:
- `trading/storage/portfolio_state.py` — PortfolioStateStore (HWM persistence)
- `scripts/migrations/add-portfolio-state.sql` — DB migration

**Files to modify**:
- `trading/risk/rules.py` — Add `PortfolioDrawdownKillSwitch` rule
- `trading/risk/config.py` — Register rule, accept `portfolio_state_store` param
- `trading/api/container.py` — Wire PortfolioStateStore
- `trading/api/routes/risk.py` — Add `GET /risk/portfolio-drawdown` endpoint

**Steps**:
1. Create PortfolioStateStore with `initialize()`, `get_state()`, `save_state()`
2. Create PortfolioDrawdownKillSwitch rule with HWM tracking, drawdown check, cooldown
3. Wire into ServiceContainer and load_risk_config
4. Add API endpoint for drawdown status
5. Migration script for `portfolio_state` table
6. Unit tests for drawdown trigger, cooldown expiry, HWM persistence

#### 2.1b: Consecutive Loss Circuit Breaker (~3h)

Tracks consecutive win/loss streaks per strategy. Auto-throttles after 5 consecutive losses.

**Files to create**:
- `scripts/migrations/add-streak-tracking.sql`

**Files to modify**:
- `trading/storage/performance.py` — Add streak fields to PerformanceSnapshot
- `trading/agents/analytics.py` — Compute streaks from trade history
- `trading/learning/strategy_health.py` — Add consecutive loss check

**Steps**: Follow plan doc §2 exactly.

#### 2.1c: Correlation Enforcement Gate (~3h)

Reduces position size when portfolio correlation exceeds thresholds.

**Files to create**:
- `trading/risk/correlation_gate.py` — CorrelationGate rule

**Files to modify**:
- `trading/risk/config.py` — Register rule with correlation_monitor
- `trading/api/container.py` — Wire CorrelationMonitor

**Steps**: Follow plan doc §3 exactly.

**Acceptance for all**: All 3 risk rules pass unit tests. Config-driven thresholds. API endpoints work. No regressions.

---

### 2.2 TP-002: Wire Signal Pipeline (4-5h)

Build miner signal aggregation with MinerConsensusAggregator.

**Current**: `feature/mission-control-backend` branch has the scaffold. Need to verify and complete.

**Files**:
- `trading/integrations/bittensor/scheduler.py` — Poll miner predictions at hash windows
- `trading/integrations/bittensor/evaluator.py` — Score predictions vs realized prices
- `trading/data/signal_bus.py` — Pub/sub for agent signals
- `trading/integrations/bittensor/miner_consensus.py` — Aggregate miner signals with sliding window

**Steps**:
1. Verify MinerConsensusAggregator from merged branch — check for completeness
2. Implement sliding window aggregation: group signals by 30-min windows, compute consensus (weighted by miner UID rank)
3. Publish consensus signals to SignalBus with type `signal.consensus`
4. Wire into `app.py` lifespan: start scheduler → poll → aggregate → publish
5. Add `GET /engine/v1/bittensor/signals` endpoint for latest consensus signals
6. Unit test: mock 3 miner signals → verify consensus calculation

**Acceptance**: MinerConsensusAggregator computes weighted consensus. Consensus signals published to SignalBus. Endpoint returns live data.

---

### 2.3 MemClaw Memory Architecture (6-8h)

8-task plan from `.sisyphus/plans/memclaw-integration.md`:

**Wave 1 (Schema + Core)**:
1. Update `memory.schema.json` with 13 types, 8 statuses, 3 visibility scopes
2. Regenerate Python/TypeScript types
3. Update LocalMemoryStore model + migration

**Wave 2 (API + Logic)**:
4. Add `/engine/v1/memory/tune` endpoint
5. Add `/engine/v1/memory/{id}/transition` endpoint
6. Update search with visibility scopes + tuning
7. Add decay scheduler logic
8. Unit tests

**Key Considerations**:
- Must maintain backward compatibility with existing `visibility` field
- Default decay windows per MemClaw spec (task=30d, episode=45d, fact=120d)
- Search tuning persisted per-agent
- Status transitions validate allowed paths

**Acceptance**: All 8 tasks completed. Existing memory data migrates cleanly. New endpoints functional. Tests green.

---

## Phase 3: Quality & Coverage (Days 8-10, ~15h)

### 3.1 Frontend Unit Tests (6-8h)

**Current**: Zero React unit tests. Only Playwright E2E tests exist.

**Priority files to test**:
1. `frontend/src/lib/api/` — API client modules (missionControl.ts, bittensor.ts)
2. `frontend/src/hooks/useMissionControl.ts` — Custom hook
3. `frontend/src/pages/` — Key page components (Lab, Forge, MissionControl)

**Setup**:
```bash
cd frontend
npm install --save-dev vitest @testing-library/react @testing-library/jest-dom jsdom
```

Add `vitest.config.ts` and `"test": "vitest"` to package.json.

**Steps**:
1. Install Vitest + Testing Library
2. Create `frontend/src/test/setup.ts` with MSW (Mock Service Worker) for API mocking
3. Write tests for:
   - `useMissionControl.ts` hook — data fetching, polling, error states
   - `missionControl.ts` API client — request formatting, response parsing
   - `Lab.tsx` — renders draft, runs backtest, shows results
   - `Forge.tsx` — form submission, validation
4. Run `cd frontend && npx vitest run`
5. Add to CI

**Acceptance**: 20+ tests covering hooks, API clients, and key components. All pass. CI includes frontend tests.

---

### 3.2 API Route Test Coverage (4-5h)

**Current**: 38+ routes, 1 integration test file. Routes largely untested.

**Priority routes** (untested or undertested):
- `arbitrage.py` — no tests
- `achievements.py` — no tests
- `shadow.py` — partial (promote needs test)
- `mission_control.py` — has tests, verify
- `drafts.py` — verify coverage
- `backtest.py` — verify coverage

**Steps**:
1. For each route file, create `tests/unit/test_routes/test_{route}.py`
2. Use `httpx.AsyncClient` with `ASGITransport` (same pattern as existing tests)
3. Mock app.state dependencies (stores, brokers, etc.)
4. Test happy path + error cases (404, 501 for unconfigured stores)
5. Add auth scope enforcement tests where `require_scope()` is used

**Acceptance**: Each priority route has ≥3 test cases. Total route test count doubles. All pass.

---

### 3.3 Fix Learning Module FIXMEs (2h)

**Problem**: `trading/learning/strategy_index.py:18` and `trading/learning/memory_linter.py:19` have FIXMEs about missing SDK methods for tag-based queries.

**Steps**:
1. Read both files, identify the exact missing method signatures
2. Implement tag-based query methods in the relevant store/interface
3. Replace FIXME comments with working implementations
4. Add unit tests

**Acceptance**: No FIXMEs in strategy_index.py or memory_linter.py. Tag-based queries work. Tests pass.

---

## Phase 4: Backlog (Days 11+, ~25h)

### 4.1 BitGet Broker Adapter (16h)

**New exchange integration**. High value for crypto trading.

**Steps** (detailed plan TBD):
1. Implement `BitGetBroker` extending broker interface
2. WebSocket feed for real-time prices
3. REST API for order execution
4. Test with BitGet testnet
5. Wire into ExchangeClient as `primary="bitget"`

### 4.2 Tax CSV Logging (8h)

Trade log export for tax compliance.

**Steps**:
1. Extend `TradeCSVLogger` with tax-relevant fields (cost basis, gain/loss, holding period)
2. Add `GET /api/v1/tax/export?year=2026&format=csv` endpoint
3. Generate Form 8949-compatible CSV
4. Unit tests with sample trade data

### 4.3 WebSocket Spreads Streaming (3-4h)

**Current**: `GET /arb/spreads` returns static data. Need event bus integration for live updates.

**Steps**:
1. Create `SpreadsEventBus` using Redis Streams
2. Wire into SpreadStore for `on_spread_update()` callback
3. Add `WS /ws/spreads` endpoint that pushes live updates
4. Frontend: add real-time spread monitoring to Mission Control

### 4.4 Knowledge Graph Real Data (3-4h)

**Current**: `KnowledgeGraph.tsx` falls back to mock data (lines 32-49) when API fails.

**Steps**:
1. Implement `GET /intelligence/graph` endpoint with real agent/memory data
2. Build `KnowledgeGraphService` that aggregates agents + memories + tasks
3. Replace mock fallback with loading state
4. Add node click → detail panel

### 4.5 AI Automation + Gamification (24h total)

6 features from plan doc:
1. Natural language trade commands (6h)
2. Achievement system expansion (4h — overlaps with 1.2)
3. Trading journal AI summaries (4h)
4. Adaptive agent parameters (4h)
5. Challenge mode (3h)
6. Social leaderboard (3h)

### 4.6 Declarative Rules Engine (8-10h)

Pre-trade validation safety net.

**Steps**:
1. Create `rules.yaml` config format
2. Parse and compile rules into checking pipeline
3. Wire into order submission flow as gateway check
4. Admin API: `GET/POST /api/v1/rules`
5. Unit tests with various rule configs

---

## Dependency Graph

```
Phase 0 (all parallel after 0.1):
  0.1 Fix test ────┐
  0.2a Merge fixes ──┤
  0.2b Merge MC ────┤──→ Phase 1 starts
  0.3 TP-015 preflight┘

Phase 1 (most parallel):
  1.1 Shadow promote ────┐
  1.2 Achievements multi ──┤
  1.3 Consolidator LLM ───┤──→ Phase 2 starts
  1.4 Lab page ────────────┤
  1.5 Arbitrage dual-leg ──┘

Phase 2 (sequential within, parallel between):
  2.1a Kill Switch ──→ 2.1b Breaker ──→ 2.1c Correlation
  2.2 Signal Pipeline (depends on 0.2b merge)
  2.3 MemClaw (independent)

Phase 3 (parallel):
  3.1 Frontend tests
  3.2 API route tests
  3.3 Learning FIXMEs

Phase 4 (independent, prioritize by business value):
  4.1-4.6 any order
```

## Time Estimates Summary

| Phase | Items | Time | Cumulative |
|-------|-------|------|-----------|
| 0 | 0.1-0.3 | 2h | 2h |
| 1 | 1.1-1.5 | 10h | 12h |
| 2 | 2.1-2.3 | 22h | 34h |
| 3 | 3.1-3.3 | 13h | 47h |
| 4 | 4.1-4.6 | 60h | 107h |

**Total estimated effort**: ~107 hours across all phases.

**Recommended execution order**: 0.1 → 0.2 → 0.3 → 1.1-1.5 (parallel) → 2.1 → 2.2 → 2.3 → 3.1-3.3 (parallel) → 4.x (as needed)