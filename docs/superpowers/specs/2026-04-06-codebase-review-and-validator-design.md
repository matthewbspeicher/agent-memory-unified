# Agent Memory Commons — Codebase Review & Bittensor Validator Design

> **Date:** 2026-04-06
> **Status:** Draft
> **Scope:** Full codebase review + Bittensor Subnet 8 validator setup
> **Strategy:** Service-by-service refactoring (Approach 3) + parallel validator track

---

## Executive Summary

A comprehensive code review of the Agent Memory Commons monorepo identified **40+ issues** across four services (Shared/Infra, Trading, API, Frontend). Critical findings include god objects exceeding 1,400 lines, duplicated code across 6+ controllers, placeholder authentication in the frontend, zero test execution in CI, and broken staging infrastructure.

Simultaneously, the existing Bittensor integration code (adapter, scheduler, evaluator, ranking, signals) is well-structured but needs infrastructure setup (wallet, registration, staking) and production hardening to run as a live Subnet 8 validator.

Work is organized into two parallel tracks:
- **Track A:** Bittensor validator deployment on WSL2 (infrastructure-focused)
- **Track B:** Codebase refactoring in 4 phases (code-focused)

---

## Track A: Bittensor Validator on WSL2

### Context

The trading service already contains a complete Bittensor integration layer:
- `trading/integrations/bittensor/adapter.py` — `TaoshiProtocolAdapter` wrapping subtensor, wallet, dendrite, metagraph
- `trading/integrations/bittensor/scheduler.py` — `TaoshiScheduler` with 30-minute hash/forward window collection
- `trading/integrations/bittensor/evaluator.py` — Miner accuracy evaluation against realized price data
- `trading/integrations/bittensor/ranking.py` — Hybrid scoring (internal accuracy + on-chain incentive)
- `trading/integrations/bittensor/derivation.py` — Consensus view derivation from miner predictions
- `trading/integrations/bittensor/signals.py` — Signal bus bridge for trading strategies
- `trading/storage/bittensor.py` — Persistence for forecasts, rankings, accuracy records
- `trading/api/routes/bittensor.py` — Status, rankings, signals API endpoints
- `trading/strategies/bittensor_signal.py` + `bittensor_consensus.py` — Trading strategies

Current state: TAO purchased on Kraken. No wallet, no registration, no validator infrastructure.

### A1. WSL2 Environment Setup

**Prerequisites on WSL2 box:**
- Python 3.11+ (3.13 preferred to match trading service)
- pip, venv
- PostgreSQL 16 client libraries (for asyncpg)
- Redis client
- Build tools (gcc, make) for bittensor native dependencies

**Install Bittensor CLI:**
```bash
pip install bittensor
btcli --version  # verify installation
```

**Install trading service dependencies:**
```bash
git clone <repo> ~/agent-memory-unified
cd ~/agent-memory-unified/trading
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### A2. Wallet Creation

```bash
# Create coldkey (this holds your TAO — protect the mnemonic)
btcli wallet new_coldkey --wallet.name sta_wallet

# Create hotkey (used for validator operations)
btcli wallet new_hotkey --wallet.name sta_wallet --wallet.hotkey sta_hotkey

# Display coldkey SS58 address for Kraken withdrawal
btcli wallet overview --wallet.name sta_wallet
```

**Security:**
- Back up the coldkey mnemonic offline (paper, hardware wallet)
- The hotkey mnemonic is less critical but should still be backed up
- Default wallet path: `~/.bittensor/wallets/`

### A3. Fund & Register

**Withdraw TAO from Kraken:**
1. Copy the coldkey SS58 address from `btcli wallet overview`
2. On Kraken: Withdraw TAO to that SS58 address
3. Wait for on-chain confirmation (~12 seconds per block on Finney)
4. Verify: `btcli wallet balance --wallet.name sta_wallet`

**Register on Subnet 8:**
```bash
btcli subnet register \
  --netuid 8 \
  --wallet.name sta_wallet \
  --wallet.hotkey sta_hotkey
```
- Registration costs ~0.1 TAO (recycle fee, varies)
- Verify: `btcli subnet list --netuid 8` should show your hotkey

**Stake TAO:**
```bash
btcli stake add \
  --wallet.name sta_wallet \
  --wallet.hotkey sta_hotkey \
  --amount <AMOUNT>
```
- More stake = more weight as validator = more influence on miner incentives
- Minimum effective stake varies by subnet competitiveness

### A4. Deploy Validator Process

**Configuration (`.env` on WSL2):**
```env
STA_BITTENSOR_ENABLED=true
STA_BITTENSOR_MOCK=false
STA_BITTENSOR_NETWORK=finney
STA_BITTENSOR_ENDPOINT=wss://entrypoint-finney.opentensor.ai:443
STA_BITTENSOR_WALLET_NAME=sta_wallet
STA_BITTENSOR_HOTKEY=sta_hotkey
STA_BITTENSOR_HOTKEY_PATH=~/.bittensor/wallets
STA_BITTENSOR_SUBNET_UID=8
STA_BITTENSOR_SELECTION_POLICY=all
STA_BITTENSOR_MIN_RESPONSES_FOR_CONSENSUS=3
STA_BITTENSOR_MIN_RESPONSES_FOR_OPPORTUNITY=3

# Database (point to Railway Postgres or local)
STA_DATABASE_URL=postgresql://user:pass@host:5432/agent_memory
STA_DATABASE_SSL=true

# Redis (point to Railway Redis or local)
STA_REDIS_URL=redis://host:6379/0

# API
STA_API_KEY=<your-api-key>
STA_API_PORT=8080
```

**Systemd service (`/etc/systemd/system/bittensor-validator.service`):**
```ini
[Unit]
Description=Agent Memory Bittensor Validator
After=network.target

[Service]
Type=simple
User=<your-user>
WorkingDirectory=/home/<user>/agent-memory-unified/trading
Environment=PATH=/home/<user>/agent-memory-unified/trading/.venv/bin:/usr/local/bin:/usr/bin
ExecStart=/home/<user>/agent-memory-unified/trading/.venv/bin/python -m uvicorn api.app:create_app --host 0.0.0.0 --port 8080 --factory
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable bittensor-validator
sudo systemctl start bittensor-validator
```

### A5. Production Gaps to Address

**Weight-setting (CRITICAL — NOT YET IMPLEMENTED):**
Validators on Bittensor must periodically call `subtensor.set_weights()` to score miners. This determines miner incentives and validator rewards. Confirmed: **no `set_weights()` call exists anywhere in the codebase.**

Implementation needed:
- Create `integrations/bittensor/weight_setter.py` with a `WeightSetter` class
- Map `MinerRanking.hybrid_score` (from `ranking.py`) to normalized weight vector
- Call `subtensor.set_weights(netuid=8, uids=uids, weights=weights, wallet=wallet)` on a configurable interval (~every 100 blocks / 20 minutes)
- Integrate into the `TaoshiScheduler` run loop or as a parallel background task
- The ranking system (`trading/integrations/bittensor/ranking.py`) already computes `hybrid_score` per miner — this is the input

**SDK Version Compatibility:**
- Current requirement: `bittensor>=8.0.0`
- Subnet 8 (Taoshi) may require specific SDK features — verify against their validator repo
- Test with `btcli subnet list --netuid 8` to confirm chain compatibility

**Connection Resilience:**
- The adapter's `connect()` method has no retry logic
- Add exponential backoff for subtensor connection failures
- Add metagraph refresh retry on network errors

### A6. Monitoring

- Existing endpoint: `GET /api/bittensor/status` returns scheduler state, evaluator state, miner counts, response rates
- Add a cron health check that hits this endpoint and alerts via Slack/WhatsApp if `healthy: false`
- Monitor validator weight-setting success via chain explorer or btcli
- Track windows_collected_total and windows_evaluated_total for drift detection

---

## Track B: Codebase Refactoring

### Audit Summary

| Service | Files Analyzed | Issues Found | Critical | High | Medium | Low |
|---------|---------------|-------------|----------|------|--------|-----|
| Shared/Infra | 15 | 9 | 2 | 3 | 3 | 1 |
| Trading | 265+ source, 265 test | 20 | 3 | 5 | 7 | 5 |
| API (Laravel) | 31 controllers, 26 models, 10 services, 63 tests | 11 | 2 | 4 | 3 | 2 |
| Frontend | 16 pages, 5 components, 7 API modules | 10 | 2 | 3 | 3 | 2 |
| **Total** | | **50** | **9** | **15** | **16** | **10** |

---

### Phase 1: Shared/Infrastructure

**Goal:** Fix the foundation that all services depend on.

#### 1.1 Unify Type Generation Pipeline

**Problem:** Two competing scripts — `scripts/sync-types.sh` and `shared/types/scripts/generate-types.sh` — with different implementations. PHP types are generated by a third script (`scripts/generate-php-types.php`) not called by either. CI only verifies TypeScript and Python types.

**Fix:**
- Consolidate into a single `scripts/generate-types.sh` that generates all three languages (Python via datamodel-codegen, TypeScript via quicktype, PHP via the existing PHP generator)
- Delete `shared/types/scripts/generate-types.sh` and `scripts/sync-types.sh`
- Update `.githooks/pre-commit` to call the unified script
- Update `.github/workflows/ci.yml` to call the unified script and verify all three language outputs

#### 1.2 Add Test Execution to CI

**Problem:** CI only runs linting (PHPStan, Ruff, tsc). No Pest, pytest, or Playwright tests execute.

**Fix:** Add three new CI jobs:
- `api-test`: `cd api && php artisan test --parallel`
- `trading-test`: `cd trading && pytest tests/unit/ -x --timeout=60`
- `frontend-test`: `cd frontend && npx playwright test`

Each job sets up its own database (PostgreSQL service container) and Redis.

#### 1.3 Pre-commit Hook Error Handling

**Problem:** `.githooks/pre-commit` silently fails if `datamodel-codegen` or `quicktype` aren't installed.

**Fix:**
```bash
#!/bin/bash
set -euo pipefail

# Check required tools
command -v datamodel-codegen >/dev/null 2>&1 || { echo "ERROR: datamodel-codegen not installed"; exit 1; }
command -v quicktype >/dev/null 2>&1 || { echo "ERROR: quicktype not installed"; exit 1; }

./scripts/generate-types.sh || { echo "ERROR: Type generation failed"; exit 1; }
git add shared/types/generated/ shared/types-py/shared_types/
```

#### 1.4 Docker Health Checks

**Problem:** No health checks on postgres/redis in either compose file. Services can start before databases are ready.

**Fix:** Add to both `docker-compose.yml` and `staging.docker-compose.yml`:
```yaml
postgres:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U postgres"]
    interval: 5s
    timeout: 5s
    retries: 5

redis:
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 5s
    retries: 5
```

Add `depends_on` with `condition: service_healthy` to api and trading services.

#### 1.5 Fix Staging Docker Compose

**Problem:** References `Dockerfile.api` and `Dockerfile.trading` which don't exist at the repo root.

**Fix:** Update `staging.docker-compose.yml` to reference actual Dockerfile paths:
- `api-service.build.dockerfile: api/Dockerfile`
- `trading-service.build.dockerfile: trading/Dockerfile`

#### 1.6 Apply Schema Drift Fixes

**Problem:** `docs/schema-drift-audit.md` documents known column gaps in `arb_spread_observations` and `arb_trades` tables.

**Fix:** Create a new Laravel migration that adds the missing columns:
- `arb_spread_observations`: add `is_claimed`, `claimed_at`, `claimed_by`
- `arb_trades`: add `sequencing`

#### 1.7 Remove Stale Migration Scripts

**Problem:** `scripts/migrate_sqlite_to_postgres.py` and `scripts/postgres-to-laravel.py` reference old structures and serve overlapping purposes.

**Fix:** Delete both. Database consolidation is complete (Phase 2 of unification was marked done). If needed again, they can be recovered from git history.

#### 1.8 Document Environment Variable Conventions

**Problem:** Inconsistent naming: Laravel uses `DB_*`/`REDIS_*`, Python uses `DATABASE_URL`/`REDIS_URL`.

**Fix:** Add a comment block at the top of `.env.example` explaining the convention:
```env
# === CONVENTIONS ===
# Laravel services use DB_HOST, DB_PORT, DB_DATABASE, DB_USERNAME, DB_PASSWORD
# Python services use DATABASE_URL (connection string format)
# Both read REDIS_URL; Laravel also reads REDIS_HOST/REDIS_PORT
# Shared auth uses JWT_SECRET (must be 256-bit / 32+ chars for HS256)
```

#### 1.9 JWT Secret Validation

**Problem:** `.env.example` shows `JWT_SECRET=CHANGE_ME_TO_256_BIT_SECRET` with no runtime enforcement.

**Fix:** Add a startup check in both `shared/auth/validate.py` and `shared/auth/JWTValidator.php` that raises/throws if `JWT_SECRET` is less than 32 characters or still contains "CHANGE_ME".

---

### Phase 2: Trading Service

**Goal:** Break up god objects, eliminate duplication, improve type safety.

#### 2.1 Decompose `api/app.py` (1,487 lines)

**Problem:** Single file handles config validation, broker init, database setup, agent runner, telemetry, background tasks, route registration, and error handlers.

**Fix:** Extract into `trading/api/startup/` modules:

| New Module | Responsibility | Approx Lines |
|---|---|---|
| `config_validation.py` | Risk, Agents, Learning config validation | ~80 |
| `broker_init.py` | Multi-broker initialization + routing | ~200 |
| `database.py` | PostgreSQL/SQLite connection setup + migrations | ~100 |
| `agents.py` | Agent runner + agent framework initialization | ~150 |
| `telemetry.py` | OpenTelemetry setup | ~60 |
| `background.py` | Background task manager setup | ~80 |
| `routes.py` | Router registration | ~50 |
| `error_handlers.py` | Exception handler registration | ~40 |
| `bittensor.py` | Bittensor adapter/scheduler/evaluator setup | ~120 |

The lifespan function in `app.py` becomes ~50 lines calling these modules in sequence.

#### 2.2 Decompose `agents/router.py` (1,473 lines)

**Problem:** `OpportunityRouter` is a god object with 20+ constructor params orchestrating 11 cross-cutting concerns: order execution, risk checking, slippage feedback, trade tracking, journal updates, shadow execution, signal features, confidence calibration, strategy health, Bittensor signals, agent evolution.

**Fix:** Extract cross-cutting concerns into event-driven hooks:

| Concern | Current | New |
|---|---|---|
| Journal updates | Direct method call | Event: `trade.executed` → `JournalListener` |
| Shadow execution | Direct method call | Event: `opportunity.approved` → `ShadowListener` |
| Signal features | Direct method call | Event: `trade.executed` → `SignalFeatureListener` |
| Confidence calibration | Direct method call | Event: `trade.closed` → `CalibrationListener` |
| Strategy health | Direct method call | Event: `trade.closed` → `StrategyHealthListener` |

The router reduces to: opportunity evaluation → risk check → order execution → trade recording → event publish. ~400 lines max.

#### 2.3 Split Config Dataclass (140+ fields)

**Problem:** `Config` is a flat dataclass with 140+ fields spanning 13 different domains.

**Fix:** Nested dataclasses:
```python
@dataclass
class Config:
    broker: BrokerConfig      # IBKR, Alpaca, Tradier settings
    api: ApiConfig            # Host, port, key
    storage: StorageConfig    # DB path, PostgreSQL URL, SSL
    llm: LLMConfig            # Anthropic, Bedrock, Groq, Ollama
    bittensor: BittensorConfig # All STA_BITTENSOR_* settings
    risk: RiskConfig          # Drawdown, Sharpe thresholds
    markets: MarketsConfig    # Kalshi, Polymarket settings
    data: DataConfig          # News, Alpha Vantage, etc.
    notifications: NotifyConfig # Slack, WhatsApp
    paper: PaperConfig        # Paper trading settings
    journal: JournalConfig    # Vector index settings
    redis: RedisConfig        # Redis URL
```

`load_config()` updated to populate nested structures. Existing `config.bittensor_enabled` becomes `config.bittensor.enabled`.

#### 2.4 Consolidate Duplicate Modules

**Problem:** `strategies/ensemble_optimizer.py` (401 lines) and `learning/ensemble_optimizer.py` (392 lines) are near-duplicates. Same for `correlation_monitor.py`.

**Fix:**
- Keep the `learning/` versions (they're the canonical location)
- Delete the `strategies/` duplicates
- Update all imports to use `learning.ensemble_optimizer` and `learning.correlation_monitor`
- Grep for any remaining references and fix

#### 2.5 Add Return Type Hints (~40 functions)

**Problem:** ~40 functions across `main.py`, `api/app.py`, `api/deps.py`, and route handlers lack return type annotations.

**Fix:** Add return types. Prioritize public functions:
- `main.py:_build_app() -> FastAPI`
- `api/app.py:lifespan() -> AsyncGenerator[None, None]`
- `api/deps.py:get_opportunity_store() -> OpportunityStore`
- All route handlers: `-> dict`, `-> JSONResponse`, `-> list[dict]`

#### 2.6 Remove Unused Imports (~15)

**Problem:** Flagged imports: `RankingConfig`, `PaperBroker`, `BrokerStream`, `CalibrationRecommendation`, `yaml` (conditional), `asyncio` in `llm/client.py`.

**Fix:** Remove each one. Run `ruff check` to catch any remaining.

#### 2.7 Standardize Dependency Injection

**Problem:** Routes mix `Depends()`, `getattr(request.app.state, ...)`, and direct imports.

**Fix:** Extend `api/container.py` to provide all dependencies via `Depends()`. Remove all `getattr(request.app.state, ...)` patterns from route handlers — these become:
```python
async def bittensor_status(store: BittensorStore = Depends(get_bittensor_store)):
```

#### 2.8 Split Large Test Files

**Problem:** `tests/unit/test_agents/test_router.py` is 1,264 lines.

**Fix:** Split into:
- `test_router_execution.py` — Order execution paths
- `test_router_risk.py` — Risk check scenarios
- `test_router_consensus.py` — Consensus logic
- `test_router_integration.py` — End-to-end flows

#### 2.9 Bittensor Production Hardening

**Problem:** Need to verify weight-setting, SDK compatibility, and connection resilience for live validator operation.

**Fix:**
- **Confirmed: `set_weights()` is NOT implemented anywhere in the codebase.** Implement a `WeightSetter` class in `integrations/bittensor/weight_setter.py` that maps `MinerRanking.hybrid_score` to on-chain weights via `subtensor.set_weights()`. This runs on a configurable interval (e.g., every 100 blocks / ~20 minutes)
- Add connection retry with exponential backoff in `TaoshiProtocolAdapter.connect()`
- Add metagraph refresh retry in `TaoshiScheduler._collect_window()`
- Pin bittensor SDK version to tested release (not just `>=8.0.0`)

#### 2.10 Conditional Dependency Validation

**Problem:** Features gated by config flags (`bittensor_enabled`, `journal_index_enabled`, `enable_arbitrage`) have no startup check that the required packages are actually installed.

**Fix:** In the startup sequence, after loading config:
```python
if config.bittensor.enabled:
    try:
        import bittensor
    except ImportError:
        raise RuntimeError("STA_BITTENSOR_ENABLED=true but bittensor package not installed")
```
Same pattern for torch/hnswlib (journal), web3 (polymarket).

---

### Phase 3: API Service (Laravel)

**Goal:** Eliminate duplication, improve validation, standardize patterns.

#### 3.1 Extract `resolveAgent()` Trait

**Problem:** Identical `resolveAgent()` method duplicated in 6 controllers (~150 lines total): MemoryController, MentionController, PresenceController, SessionController, SubscriptionController, TaskController.

**Fix:** Create `app/Traits/ResolvesAgent.php`:
```php
trait ResolvesAgent {
    protected function resolveAgent(Request $request): Agent {
        $agent = $request->attributes->get('agent');
        if (!$agent) {
            abort(401, 'Agent not authenticated');
        }
        return $agent;
    }
}
```
Replace all 6 inline implementations with `use ResolvesAgent;`.

#### 3.2 Extract Workspace Validation Trait

**Problem:** `agentBelongsToWorkspace()` duplicated in 4 controllers.

**Fix:** Create `app/Traits/ValidatesWorkspaceMembership.php`:
```php
trait ValidatesWorkspaceMembership {
    protected function ensureAgentInWorkspace(Agent $agent, Workspace $workspace): void {
        if (!$workspace->agents()->where('agents.id', $agent->id)->exists()) {
            abort(403, 'Agent is not a member of this workspace');
        }
    }
}
```

#### 3.3 Split MemoryController (555 lines)

**Problem:** 13 methods handling CRUD, search, commons, sharing, and feedback.

**Fix:**
- `MemoryController` (CRUD): store, show, index, update, destroy, compact (~200 lines)
- `MemorySearchController`: search, commonsIndex, commonsSearch (~150 lines)
- `MemorySharingController`: share, feedback (~100 lines)

Update `routes/api.php` to point to new controllers.

#### 3.4 Create FormRequest Classes

**Problem:** 28+ controllers have inline validation rules instead of dedicated FormRequest classes.

**Fix:** Create FormRequests for the most repeated validations:
- `StoreMemoryRequest` — value, type, visibility, tags, metadata rules
- `UpdateMemoryRequest` — same fields, optional
- `CreateTaskRequest` — title, description, workspace validation
- `UpdateTaskRequest` — status, assignee validation
- `CreateWebhookRequest` — url, events, secret validation
- `StoreMentionRequest` — content, workspace, mentioned_agent validation

#### 3.5 Extract Trading Stats Service

**Problem:** `TradingStatsController` has duplicated SELECT logic between `byTicker()` (lines 53-58) and `byStrategy()` (lines 85-90) — identical `selectRaw` for trade counts, win rate, profit factor, total PnL.

**Fix:** Create `TradingStatsService::buildStatsQuery(Agent $agent, string $groupBy, bool $paper): Builder` that returns the base query. Each method adds only its unique groupBy clause.

#### 3.6 Standardize Error Responses

**Problem:** Controllers use 3 different error patterns: `response()->json(['error' => ...])`, `abort()`, and custom response methods.

**Fix:** Create `app/Traits/ApiResponses.php`:
```php
trait ApiResponses {
    protected function success(mixed $data, int $status = 200): JsonResponse { ... }
    protected function error(string $message, int $status = 422): JsonResponse { ... }
    protected function notFound(string $resource = 'Resource'): JsonResponse { ... }
}
```
Apply to all API controllers.

#### 3.7 Add Missing Transaction Boundaries

**Problem:** `TaskController.store()`, `MentionController.store()`, and similar multi-write operations don't wrap in transactions.

**Fix:** Wrap operations that create a record AND publish an event/update a related model in `DB::transaction()`.

#### 3.8 Split MemoryService (434 lines)

**Problem:** Handles CRUD, search, embedding generation, summarization, quota checks.

**Fix:**
- `MemoryService` — store, update, delete, compact, quota checks (~250 lines)
- `MemorySearchService` — search, getRelated, embedding-based queries (~180 lines)

---

### Phase 4: Frontend

**Goal:** Fix security, improve reliability, extract reusable patterns.

#### 4.1 Fix Authentication

**Problem:** `src/lib/auth.ts` has hardcoded mock user (`agent@remembr.dev`), no token verification on app load, no refresh logic.

**Fix:**
- On app load, verify token by hitting `GET /api/v1/auth/me` (or similar)
- If token is expired/invalid, redirect to login
- Remove hardcoded mock user data
- Add token refresh logic using JWT refresh endpoint
- Keep localStorage for token storage (acceptable for this app type) but add XSS-safe patterns

#### 4.2 Add Error Boundaries

**Problem:** Any unhandled error crashes the entire React app — no recovery possible.

**Fix:**
- Create `src/components/ErrorBoundary.tsx` with:
  - Friendly error message
  - "Try again" button that resets the boundary
  - Optional error reporting
- Wrap in `App.tsx` at the top level
- Add per-route boundaries for lazy-loaded pages in `router.tsx`

#### 4.3 Extract `<QueryWrapper>` Component

**Problem:** Every page repeats the same loading/error/empty pattern (~40 instances):
```tsx
{isLoading && <div>Loading...</div>}
{error && <div>Error: {error.message}</div>}
{data && data.length === 0 && <div>No items</div>}
```

**Fix:** Create `src/components/QueryWrapper.tsx`:
```tsx
<QueryWrapper query={agentsQuery} emptyMessage="No agents found">
  {(data) => <AgentList agents={data} />}
</QueryWrapper>
```
Handles loading skeleton, error display, and empty state uniformly.

#### 4.4 Extract Modal Form Hook

**Problem:** `Webhooks.tsx` (238 lines) and `WorkspaceList.tsx` (164 lines) have nearly identical modal + form state + mutation + invalidation patterns (~70 lines duplicated).

**Fix:** Create `src/hooks/useModalForm.ts`:
```tsx
const { isOpen, open, close, form, setField, submit, isSubmitting } = useModalForm({
  initialValues: { name: '', url: '' },
  mutationFn: createWebhook,
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['webhooks'] }),
});
```

#### 4.5 Convert Landing Page to TanStack Query

**Problem:** `Landing.tsx` uses raw `fetch()` + `setInterval()` for polling instead of TanStack Query's `refetchInterval`.

**Fix:**
```tsx
const { data: stats } = useQuery({
  queryKey: ['platform-stats'],
  queryFn: () => api.get('/stats').then(r => r.data),
  refetchInterval: 30_000,
});
```
Remove the manual `useEffect` + `setInterval` + cleanup.

#### 4.6 Consolidate Color Mapping

**Problem:** Two separate color-from-string implementations — `Landing.tsx:44-51` (array lookup) and `AgentBadge.tsx:11-22` (HSL computation).

**Fix:** Keep the `AgentBadge` HSL approach (more unique colors). Export a `getAgentColor(name: string): string` utility from a shared module. Delete the Landing.tsx version.

#### 4.7 Fix E2E Test Assertions

**Problem:** Tests assert text that doesn't match the actual UI:
- `auth.spec.ts` expects "Welcome Back" but Login.tsx renders "Login"
- `core.spec.ts` expects "Trade Ledger" but TradeHistory.tsx renders "Trade History"

**Fix:** Update test assertions to match current UI text. Run Playwright to verify all pass.

#### 4.8 Type the KnowledgeGraph Ref

**Problem:** `useRef<any>(null)` in KnowledgeGraph.tsx.

**Fix:** Import the ForceGraph3D instance type and use it:
```tsx
const graphInstance = useRef<ForceGraph3DInstance | null>(null);
```

#### 4.9 Add Pagination

**Problem:** Leaderboard, Commons, and TradeHistory load unbounded result sets.

**Fix:** Add cursor-based or offset pagination:
- API already likely supports `?page=` or `?cursor=` params
- Add "Load more" button or infinite scroll using TanStack Query's `useInfiniteQuery`
- Start with Leaderboard and Commons (highest volume)

#### 4.10 Extract UI Component Library

**Problem:** Button styles, modal backdrops, card styles, and input styles are repeated with inconsistent spacing/colors across 15+ files.

**Fix:** Create `src/components/ui/` with:
- `Button.tsx` — primary, secondary, danger variants using `.neural-button-*` classes
- `Modal.tsx` — standardized backdrop, close button, title
- `Card.tsx` — wraps `.neural-card` with consistent padding
- `Input.tsx` — wraps `.neural-input` with label and error display

Replace inline usage across all pages.

---

## Dependency Graph

```
Phase 1 (Shared/Infra)
  ├── 1.1-1.3: Type generation + CI (no deps)
  ├── 1.4-1.5: Hooks + Docker (no deps)
  ├── 1.6: Staging compose (depends on 1.5)
  ├── 1.7-1.8: Cleanup (no deps)
  └── 1.9: Schema drift fix (no deps)

Phase 2 (Trading) — depends on Phase 1 completion
  ├── 2.1: Decompose app.py (no deps)
  ├── 2.2: Decompose router.py (no deps)
  ├── 2.3: Split Config (depends on 2.1 for startup module structure)
  ├── 2.4: Consolidate duplicates (no deps)
  ├── 2.5-2.6: Type hints + unused imports (no deps, can parallelize)
  ├── 2.7: DI standardization (depends on 2.1)
  ├── 2.8: Split test files (no deps)
  ├── 2.9: Bittensor hardening (depends on 2.1 for startup module)
  └── 2.10: Dependency validation (depends on 2.1, 2.3)

Phase 3 (API) — can run in parallel with Phase 2
  ├── 3.1-3.2: Extract traits (no deps)
  ├── 3.3: Split MemoryController (depends on 3.1)
  ├── 3.4: FormRequests (no deps)
  ├── 3.5: TradingStatsService (no deps)
  ├── 3.6: ApiResponses trait (no deps)
  ├── 3.7: Transaction boundaries (no deps)
  └── 3.8: Split MemoryService (no deps)

Phase 4 (Frontend) — depends on Phase 3 (API changes may affect endpoints)
  ├── 4.1: Fix auth (no deps)
  ├── 4.2: Error boundaries (no deps)
  ├── 4.3: QueryWrapper (no deps)
  ├── 4.4: useModalForm hook (no deps)
  ├── 4.5-4.6: Landing + colors (no deps)
  ├── 4.7: Fix tests (depends on any UI text changes)
  ├── 4.8: Type ref (no deps)
  ├── 4.9: Pagination (depends on API pagination support)
  └── 4.10: UI components (no deps, but do last — touches many files)

Track A (Validator) — fully independent, runs in parallel with all phases
  ├── A1-A2: Setup + wallet (no deps)
  ├── A3: Fund + register (depends on A2)
  ├── A4: Deploy (depends on A3, benefits from 2.9)
  └── A5: Monitoring (depends on A4)
```

---

## Success Criteria

| Track/Phase | Done When |
|---|---|
| **Track A** | Validator is registered on Subnet 8, collecting miner predictions every 30 minutes, and setting weights on-chain |
| **Phase 1** | Single type generation script, CI runs all test suites, Docker starts cleanly with health checks |
| **Phase 2** | No file >500 lines in trading service, Config is nested, no duplicate modules, all functions typed |
| **Phase 3** | No duplicated `resolveAgent()`, all validation in FormRequests, consistent error responses |
| **Phase 4** | Real auth verification, error boundaries catch crashes, no duplicated query state rendering |
| **Overall** | `git diff --stat` shows net negative lines (code removed > code added) |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Bittensor SDK version incompatible with Subnet 8 | Medium | High | Test on testnet before mainnet; check Taoshi's validator requirements doc |
| Router decomposition breaks trading logic | Medium | High | Comprehensive test coverage before refactoring; feature-flag new event bus |
| Config restructuring breaks environment loading | Medium | Medium | Write migration tests; keep backward-compat for flat STA_ vars |
| FormRequest extraction changes validation behavior | Low | Medium | Run existing Pest test suite after each controller change |
| TAO insufficient for effective validator stake | Unknown | Medium | Check current Subnet 8 minimum effective stake before committing |

---

## Out of Scope

- New features (no new endpoints, pages, or integrations)
- Database schema redesign (beyond documented drift fixes)
- Migration from Railway to another host
- Frontend redesign or new pages
- Upgrading framework versions (Laravel 12, React 19 are current)
