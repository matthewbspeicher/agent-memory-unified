# Codebase Hardening v2 — Security, Integrity, Simplification & Module Boundaries

**Date:** 2026-04-02
**Status:** Approved
**Scope:** 19 critical fixes, 16 important fixes, 11 simplifications, 1 structural reorganization

---

## Context

A review of 35 commits (138 files, ~9,500 lines) added in the last 24 hours surfaced significant issues across security, authorization, data integrity, and code organization. Eight parallel review agents analyzed the codebase and produced findings that this spec addresses comprehensively.

The codebase has grown to 30 API controllers, 23 trading routes (38% of API surface), and 4 major feature verticals (memories, collaboration, arena, trading). The rapid growth introduced duplicated code patterns, auth gaps, dead/broken functionality, and inconsistent conventions.

---

## Phase 1 — Security Criticals

All items in this phase are deployment-blocking. They must ship before any other work.

### S1: Token Storage Hardening (Staged Rollout Required)

**Problem:** Three places query plaintext tokens with `orWhere('api_token', $token)` fallbacks that defeat the partial hashing implementation. Database compromise exposes all tokens.

**Files:**
- `app/Providers/AppServiceProvider.php:45` — agent guard queries `api_token` directly, missing `str_starts_with($token, 'amc_')` check
- `app/Http/Middleware/AuthenticateAgent.php:34` — workspace lookup has `orWhere('api_token', $token)`
- `app/Http/Controllers/Api/AgentController.php:27` — owner lookup has `orWhere('api_token', ...)`
- `app/Http/Controllers/Api/AgentController.php:47` — `Agent::create(['api_token' => $token, ...])` will break after S5 removes from `$fillable`
- `app/Models/Workspace.php:85-93` — `ensureApiToken()` stores and returns plaintext `$this->api_token`

**This is a STAGED ROLLOUT — three separate deployments with production verification between each:**

#### S1.1: Backfill Hashes (Migration Only)

Deploy migration `backfill_token_hashes`:
```php
Agent::whereNull('token_hash')->whereNotNull('api_token')
    ->chunk(100, fn($agents) => $agents->each(fn($agent) =>
        $agent->update(['token_hash' => hash('sha256', $agent->api_token)])
    ));

User::whereNull('api_token_hash')->whereNotNull('api_token')
    ->chunk(100, fn($users) => $users->each(fn($user) =>
        $user->update(['api_token_hash' => hash('sha256', $user->api_token)])
    ));

Workspace::whereNull('api_token_hash')->whereNotNull('api_token')
    ->chunk(100, fn($workspaces) => $workspaces->each(fn($ws) =>
        $ws->update(['api_token_hash' => hash('sha256', $ws->api_token)])
    ));

// Assert zero nulls remain
if (Agent::whereNull('token_hash')->whereNotNull('api_token')->exists()) {
    throw new \Exception('Some agents still have null token_hash');
}
// ... repeat for users and workspaces
```

**Verify:** `SELECT COUNT(*) FROM agents WHERE token_hash IS NULL AND api_token IS NOT NULL` returns 0.

**Rollback:** No-op — this only adds data, doesn't remove anything.

#### S1.2: Switch to Hash-Only Lookups (Code Change)

Deploy code that reads from hash columns only:

1. **`AppServiceProvider.php:45`** — preserve `amc_` prefix check:
   ```php
   if (! str_starts_with($token, 'amc_')) return null;
   return Agent::where('token_hash', hash('sha256', $token))
       ->where('is_active', true)->first();
   ```

2. **`AuthenticateAgent.php:34`** — remove `orWhere`:
   ```php
   $workspace = Workspace::where('api_token_hash', $tokenHash)->first();
   ```

3. **`AgentController.php:27`** — remove `orWhere`:
   ```php
   $owner = User::where('api_token_hash', $tokenHash)->first();
   ```

4. **`AgentController.php:47`** — stop writing `api_token` (before S5 removes from `$fillable`):
   ```php
   $agent = Agent::create([
       'token_hash' => hash('sha256', $token),
       // Remove 'api_token' => $token
       // ... other fields
   ]);
   ```

5. **`Workspace.php:85-93`** — only return token at creation:
   ```php
   if (! $this->api_token_hash) {
       $token = static::generateToken();
       $this->update(['api_token_hash' => hash('sha256', $token)]);
       return $token; // Return immediately, don't store plaintext
   }
   throw new \LogicException('Token already exists — cannot retrieve after creation');
   ```

**Verify:** Monitor auth success rate for 48 hours. All auth works (reads hash, plaintext unused but still in DB).

**Rollback:** Revert code deploy. Plaintext columns still exist.

#### S1.3: Drop Plaintext Columns (Migration)

Deploy migration `drop_plaintext_token_columns`:
```php
Schema::table('agents', fn($table) => $table->dropColumn('api_token'));
Schema::table('users', fn($table) => $table->dropColumn('api_token'));
Schema::table('workspaces', fn($table) => $table->dropColumn('api_token'));
```

**Verify:** Full auth flow works for 24 hours.

**Rollback:** Cannot rollback — column drop is permanent.

**Risk:** Staging as three deployments with verification gates dramatically reduces risk. Column drop only happens after 48 hours of proven hash-only auth.

### S2: Auth Bypass for Non-JSON Requests

**Problem:** `AuthenticateAgent.php:27-28` — when no bearer token and request doesn't `expectsJson()`, calls `$next($request)`, passing unauthenticated requests to controllers.

**Fix:** Always return 401 when no token is provided, regardless of `Accept` header. Remove the `expectsJson()` branching. Also remove duplicate `$request->bearerToken()` call at line 16.

**File:** `app/Http/Middleware/AuthenticateAgent.php`

### S3: Scope Enforcement Null Pass-Through

**Problem:** `EnforceAgentScopes.php:18` — `if ($agent && !$agent->hasScope(...))` silently passes when `$agent` is null.

**Fix:** Return 401 when `$agent` is null. The middleware is only applied to routes requiring a scope, so missing agent is always an error.

**File:** `app/Http/Middleware/EnforceAgentScopes.php`

### S4: Exception Message Leaks

**Problem:** Three catch blocks in `AuthenticateAgent.php` return `$e->getMessage()` to clients, exposing file paths, SQL, and class names.

**Fix:** Return generic `"Authentication failed."` in all three catch blocks. The existing `Log::warning` calls already capture details server-side.

**File:** `app/Http/Middleware/AuthenticateAgent.php`

### S5: Mass-Assignable Security Fields

**Problem:** `Agent.$fillable` includes `api_token`, `token_hash`, `is_active`, `max_memories`, `scopes`. `Workspace.$fillable` includes `api_token`, `api_token_hash`.

**Fix:** Remove from `$fillable`:
- `Agent`: `api_token`, `token_hash`, `is_active`, `max_memories`, `scopes`
- `Workspace`: `api_token`, `api_token_hash`

**Callsites requiring updates:**
- `AgentController::register()` L43-49 — passes `token_hash` via `Agent::create()`, change to:
  ```php
  $agent = new Agent($validated);
  $agent->token_hash = hash('sha256', $token);
  $agent->save();
  ```
- `Agent::touchLastSeen()` L162 — calls `updateQuietly(['last_seen_at' => now()])`. `last_seen_at` must stay in `$fillable` or this breaks. Do NOT remove `last_seen_at`.

Grep all `Agent::create`, `Agent::update`, `$agent->update`, `Workspace::create`, `Workspace::update` for other callsites passing these fields.

**Files:** `app/Models/Agent.php`, `app/Models/Workspace.php`, `app/Http/Controllers/Api/AgentController.php`

### S6: CSRF Bypass with Fake Token Prefix

**Problem:** `ValidateAgentCsrf.php:16` skips CSRF for any request with a `Bearer` token starting with `amc_` or `wks_`, without validating the token is real.

**Fix Options:**

**Option A (Recommended):** Audit which routes actually use this middleware. If all agent API calls are in the `api` middleware group (which is CSRF-exempt by default), delete `ValidateAgentCsrf` entirely and remove it from `bootstrap/app.php`.

**Option B:** If some legitimate web routes need agent bearer token support (e.g., Inertia endpoints with agent auth), move the CSRF skip to AFTER token validation. The middleware becomes:
```php
// Validate token first via AuthenticateAgent
if (request()->attributes->has('agent')) {
    return $next($request); // Valid agent, skip CSRF
}
// Fall through to normal CSRF validation
return parent::handle($request, $next);
```

**Action:** Audit `routes/web.php` for agent-authenticated endpoints. If none exist, choose Option A. If they do, choose Option B.

**File:** `app/Http/Middleware/ValidateAgentCsrf.php`, `bootstrap/app.php`

### S7: `hasScope()` HTTP Coupling

**Problem:** `Agent::hasScope()` reads `request()->attributes->has('agent')` to grant humans full access. Couples the model to the HTTP cycle.

**Fix:** The method becomes pure, but we must audit all callsites outside middleware first:

```php
public function hasScope(string $scope): bool
{
    return in_array($scope, $this->scopes ?? []);
}
```

**BEFORE applying this fix, audit all `hasScope()` callsites:**
- Grep for `->hasScope(` across the codebase
- Any calls outside of `EnforceAgentScopes` middleware that expect humans to pass need alternative handling
- If found, those callsites should check `Auth::guard('web')->check()` explicitly before calling `hasScope()`

**Current behavior:** Human session users bypass all scope checks. After this fix, calling `$agent->hasScope()` on behalf of a human will check the actual `scopes` array, which may deny access the human previously had.

**Mitigation:** The `EnforceAgentScopes` middleware (which calls `hasScope()`) only fires on routes where it's explicitly applied. If a route is agent-authenticated, it won't have a human session. So this is safe IF no controller code calls `hasScope()` directly for human users.

**Action:** Audit before implementation. If human-context `hasScope()` calls exist, refactor them first.

**File:** `app/Models/Agent.php` plus any controllers calling `hasScope()` directly

---

## Phase 2 — Broken Functionality

Items that crash or silently do nothing in production.

### T1: Register `EvaluateTradeAlerts` Listener

**Problem:** `EvaluateTradeAlerts` has handler methods but is never registered. All trade alerts are silently dead.

**Fix:** Add to `AppServiceProvider::boot()`:
```php
Event::listen(TradeClosed::class, [EvaluateTradeAlerts::class, 'handleTradeClosed']);
Event::listen(TradeOpened::class, [EvaluateTradeAlerts::class, 'handleTradeOpened']);
```

Also fix `pnl == 0` edge case (I15): change `if ($pnl > 0) ... else` to `if ($pnl > 0) ... elseif ($pnl < 0)` so break-even trades don't trigger `pnl_below`.

**Files:** `app/Providers/AppServiceProvider.php`, `app/Listeners/EvaluateTradeAlerts.php`

### T2: Fix Wrong Webhook Listener

**Problem:** `ProcessSemanticWebhooks` (weaker duplicate) is registered for `MemoryCreated` instead of `EvaluateSemanticWebhooks`. Also leaks private memory summaries in payloads.

**Fix:**
1. Change `AppServiceProvider` to register `EvaluateSemanticWebhooks` instead of `ProcessSemanticWebhooks`
2. Delete `app/Listeners/ProcessSemanticWebhooks.php`
3. Verify `EvaluateSemanticWebhooks` handles null embeddings gracefully

**Files:** `app/Providers/AppServiceProvider.php`, `app/Listeners/ProcessSemanticWebhooks.php` (delete), `app/Listeners/EvaluateSemanticWebhooks.php` (verify)

### T3: Fix `auto-compact` Command

**Problem:** `AutoCompactMemories.php:62` calls `MemoryService::compact()` which doesn't exist. Crashes every invocation.

**Fix:** Extract compaction logic from `MemoryController::compact()` into `MemoryService::compact(Agent $agent, array $memoryIds, string $summaryKey): Memory`. The command and controller both call the service method.

**Files:** `app/Services/MemoryService.php`, `app/Console/Commands/AutoCompactMemories.php`, `app/Http/Controllers/Api/MemoryController.php`

### T4: Trading Score Migration

**Problem:** `TradingService::recalculateStats()` stores `trading_score` in `ArenaProfile.personality_tags` JSON column as an acknowledged hack.

**Fix:**
1. New migration: `add_trading_score_to_arena_profiles_table` — adds nullable `trading_score` decimal column
2. Data migration: reads `personality_tags['trading_score']`, writes to new column, removes key from JSON
3. Update `TradingService::recalculateStats()` to write `$profile->trading_score` directly
4. Update any reads of `personality_tags['trading_score']`

**Files:** New migration, `app/Services/TradingService.php`, any ArenaProfile consumers

### I14: `EnforcePlanLimits` Middleware Decision

**Problem:** No-op middleware — `handle()` immediately returns `$next($request)`. Applied to every authenticated route, giving false confidence.

**Decision:** Since billing exists (`BillingController`, Stripe integration), this should be **implemented**, not deleted. But implementation is separate feature scope.

**Fix:** Remove the middleware from routes AND delete the alias. Don't keep a dangling file with no registration — confuses future developers.

**Action:**
1. Remove `plan.limits` middleware from all routes in `routes/api.php`
2. Remove alias from `bootstrap/app.php`
3. Delete `app/Http/Middleware/EnforcePlanLimits.php`
4. Add comment in `routes/api.php`: `// TODO: Implement plan limits enforcement as new middleware when needed`

Reimplementation is a future feature — start fresh with correct design rather than keep broken skeleton.

**Files:** `routes/api.php`, `bootstrap/app.php`, `app/Http/Middleware/EnforcePlanLimits.php` (delete)

---

## Phase 3 — Authorization & Data Integrity

### Collaboration Auth Gaps

**C1 + C2: Task update/assign/status authorization**

Add TWO checks: (1) agent is in task's workspace, (2) agent is creator or assignee.

In `TaskController::update`, `assign`, and `updateStatus` — after existing workspace membership check:
```php
// Verify task belongs to the workspace being accessed
if ($task->workspace_id !== $workspace->id) {
    return response()->json(['error' => 'Task not found in this workspace.'], 404);
}

// Verify agent has permission to modify this task
if ($task->created_by_agent_id !== $agent->id && $task->assigned_agent_id !== $agent->id) {
    return response()->json(['error' => 'Only the task creator or assignee can modify this task.'], 403);
}
```

For `updateStatus`: restrict `completed`/`failed` to assignee only; `cancelled` can be set by creator:
```php
if ($status === 'completed' || $status === 'failed') {
    if ($task->assigned_agent_id !== $agent->id) {
        return response()->json(['error' => 'Only the assignee can mark a task as completed/failed.'], 403);
    }
}
```

**File:** `app/Http/Controllers/Api/TaskController.php`

**C3: `MentionController::respond` missing workspace membership check**

Add `agentBelongsToWorkspace()` call before the `target_agent_id` check.

**File:** `app/Http/Controllers/Api/MentionController.php`

**I3: Events endpoint ignores subscriptions**

Filter events by the agent's active subscription `event_types`:
```php
$subscribedTypes = $agent->workspaceSubscriptions()
    ->where('workspace_id', $workspace->id)
    ->where('is_active', true)
    ->pluck('event_types')
    ->flatten()
    ->unique()
    ->toArray();
$query->whereIn('event_type', $subscribedTypes);
```

Return empty result if no active subscriptions.

**File:** `app/Http/Controllers/Api/SubscriptionController.php`

**I4: Mentions can be responded to multiple times**

Add `isPending()` guard in `CollaborationMention::respond()`. Controller catches `\LogicException` and returns 422.

**Files:** `app/Models/CollaborationMention.php`, `app/Http/Controllers/Api/MentionController.php`

**I5: `WorkspaceTest` tests nonexistent `slug` column**

Remove `slug` references from test. Test only fields in `$fillable` and migration.

**File:** `tests/Unit/Models/WorkspaceTest.php`

### Arena Data Integrity

**A1: ELO float truncation**

Wrap both updates: `(int) round($elo1 + $k * ($actual1 - $expected1))`.

**File:** `app/Services/BattleArenaService.php`

**A2: Tournament join race condition**

Wrap `joinTournament` in `DB::transaction` + `lockForUpdate`. Add participant capacity validation inside lock.

**Capacity tracking:** Tournament capacity is not currently stored. Options:
1. Add `max_participants` column to `arena_tournaments` table (recommended)
2. Use a constant (e.g., 32 for single-elimination bracket sizes)

**Fix with Option 1:**
```php
DB::transaction(function () use ($tournament, $agent) {
    $tournament = ArenaTournament::lockForUpdate()->findOrFail($tournament->id);
    if ($tournament->status !== 'open') {
        abort(422, 'Tournament is not open for registration.');
    }
    $currentCount = $tournament->participants()->count();
    if ($tournament->max_participants && $currentCount >= $tournament->max_participants) {
        abort(422, 'Tournament is full.');
    }
    $agent->arenaTournaments()->syncWithoutDetaching([$tournament->id]);
});
```

**Files:** `app/Services/BattleArenaService.php`, new migration for `max_participants` column

**A3: Tournament state corruption**

Validate participant count before setting status to `in_progress`. Add max-rounds safeguard (10 rounds) — after max, highest cumulative score wins.

```php
public function processTournamentRound(ArenaTournament $tournament): void
{
    $participants = $tournament->participants()->where('status', 'active')->get();

    if ($participants->count() < 2) {
        $tournament->update(['status' => 'completed']);
        return;
    }

    $tournament->update(['status' => 'in_progress']);

    // Track rounds to prevent infinite all-draw stall
    $currentRound = $tournament->current_round ?? 0;
    if ($currentRound >= 10) {
        // Force termination: highest score wins
        $winner = $tournament->participants()
            ->where('status', 'active')
            ->orderBy('score', 'desc')
            ->first();
        if ($winner) {
            $winner->pivot->update(['status' => 'winner']);
        }
        $tournament->update(['status' => 'completed']);
        return;
    }

    $tournament->update(['current_round' => $currentRound + 1]);

    // ... existing match logic
}
```

**Files:** `app/Services/BattleArenaService.php`, migration to add `current_round` column to `arena_tournaments`

**A4: Tournament uses unofficial challenges**

Extract `ArenaChallenge::scopeOfficial()`:
```php
public function scopeOfficial($query) {
    return $query->whereHas('gym', fn($q) => $q->where('is_official', true));
}
```

Both `requestMatch` and `processTournamentRound` use `ArenaChallenge::official()->inRandomOrder()->first()`.

**Files:** `app/Models/ArenaChallenge.php`, `app/Services/BattleArenaService.php`, `app/Http/Controllers/Api/ArenaMatchController.php`

**A5: Zero-vector embedding**

Replace inline zero-vector `Memory::create()` in `awardTournamentRewards` with a dispatched job so `EmbeddingService` generates the real vector asynchronously. Create memory without embedding, let job backfill.

**File:** `app/Services/BattleArenaService.php`

**I10: `ReflectionMethod` hack**

Extract `callGemini` as a public method on `SummarizationService` (or a new `GeminiClient` service). Inject normally into `BattleArenaService`.

**Files:** `app/Services/BattleArenaService.php`, `app/Services/SummarizationService.php` (or new `GeminiClient`)

**I11: Unbounded `ArenaGym::all()` on WEB controller**

**Note:** This is in the WEB controller (`app/Http/Controllers/ArenaController.php`), NOT the API controller. The API controller (`app/Http/Controllers/Api/ArenaGymController.php`) correctly filters to `is_official`.

Change web controller to `ArenaGym::where('is_official', true)->get()`. Fix `recentMatches` stub to query actual recent matches.

**File:** `app/Http/Controllers/ArenaController.php` (web controller)

**I12: `show` exposes unofficial gyms**

Add `where('is_official', true)` to `show` query.

**File:** `app/Http/Controllers/Api/ArenaGymController.php`

**I13: Double `fresh()` calls**

Call once, store in `$refreshed`, use for both fields.

**File:** `app/Http/Controllers/Api/ArenaChallengeController.php`

### Trading Logic Bugs

**I6: N+1 on leaderboard**

Add `->with('agent')` before `->get()`.

**File:** `app/Http/Controllers/Api/TradingLeaderboardController.php`

**I7: Stale model in `SummarizeMemory`**

Add `$this->memory->refresh()` before the summary guard.

**File:** `app/Jobs/SummarizeMemory.php`

**I8: Raw `$request->input('paper')` bypasses validation**

Change to `$validated['paper'] ?? true`.

**File:** `app/Http/Controllers/Api/TradingController.php`

**I9: `TradeCorrelationTest` missing `RefreshDatabase`**

Add `uses(RefreshDatabase::class)` and mock `EmbeddingService`.

**File:** `tests/Feature/TradeCorrelationTest.php`

**I16: `Auth::guard('web')->setUser()` side-effect**

Remove from `AuthenticateAgent`. API bearer token auth should not log in the owner on the web guard.

**File:** `app/Http/Middleware/AuthenticateAgent.php`

---

## Phase 4 — Deduplication & Simplification

### 4A: `ResolvesAgent` Trait

Create `app/Concerns/ResolvesAgent.php` with:
- `resolveAgent(Request $request): Agent|JsonResponse`
- `agentBelongsToWorkspace(Agent $agent, Workspace $workspace): bool`
- `resolveWorkspaceAgent(Request $request, Workspace $workspace): Agent|JsonResponse` — combines workspace membership + agent resolution

Delete local copies from: `MemoryController`, `SessionController`, `PresenceController`, `MentionController`, `TaskController`, `SubscriptionController`.

Standardize error message to `'No valid authentication context found.'` across all controllers.

### 4B: Route Model Binding for Workspaces

Change workspace routes from `{id}` to `{workspace}` in `routes/api.php`. Type-hint `Workspace $workspace` in controller method signatures. Remove all `Workspace::find($id)` + 404 guard blocks (~20 occurrences across 4 controllers).

### 4C: `$request->boolean()` Replacement

Replace all 15 instances of `filter_var($request->input('paper', ...), FILTER_VALIDATE_BOOLEAN)` with `$request->boolean('paper', true)` in:
- `TradingController.php` (1)
- `TradingStatsController.php` (5)
- `TradingLeaderboardController.php` (2)
- `TradingPositionController.php` (2)
- `PortfolioController.php` (1)
- `TradeExportController.php` (1)
- `ReplayController.php` (1)
- `RiskController.php` (2)

### 4D: Response Envelope Standardization

Add helper to base `Controller.php`:
```php
protected function ok($data, int $status = 200): JsonResponse
{
    return response()->json(['data' => $data], $status);
}
```

Apply across all controllers during Phase 5 restructuring. Paginated endpoints use Laravel's built-in paginator `toArray()` (already wraps `data` + `meta`).

### 4E: Business Logic Extraction

| From | To | Logic |
|------|----|-------|
| `TradingStatsController` | `TradingQueryService` | Raw SQL aggregations, Pearson correlation |
| `LeaderboardApiController::active` | `LeaderboardService::calculateStreak()` | 30-day streak calculation |
| `PortfolioController::index` | `PortfolioService::aggregate()` | Weighted average, cross-agent rollup |
| `WebhookController::store` | `WebhookService::create()` | Embedding generation side-effect |

Extract as-is, no behavior changes. Controllers become thin validate → service → respond wrappers.

### 4F: Controller Consolidation

| Merge | Into |
|-------|------|
| `AchievementController` (16 lines, 1 method) | `AgentController` |
| `ArenaGymController` + `ArenaProfileController` | Single `Api\ArenaController` |
| `StatsController` + `CommonsPollController` | New `CommonsController` |

### 4G: Python SDK Deduplication

Extract `_BaseClient` with all method bodies. `RemembrClient` and `AsyncRemembrClient` each implement only `_request()`. Eliminates ~350 lines.

### 4H: SDK HTTP Method Fixes

- Python `respond_to_mention`: `PUT` → `POST`
- Python `assign_task`: `PUT` → `POST`

### 4I: `HasSecureToken` Trait

Create `app/Concerns/HasSecureToken.php`:
```php
trait HasSecureToken {
    abstract protected function tokenPrefix(): string;
    abstract protected function tokenLength(): int;

    public static function generateToken(): string { ... }
    public static function hashToken(string $token): string { ... }
    public function ensureApiToken(): void { ... }
}
```

Apply to `Agent` (prefix `amc_`, length 60) and `Workspace` (prefix `wks_`, length 40). Replace all inline `hash('sha256', ...)` calls.

---

## Phase 5 — Trading Module Boundary

### Directory Structure

```
app/Trading/
  Controllers/
    TradingController.php
    TradingStatsController.php
    TradingLeaderboardController.php
    TradingPositionController.php
    TradeAlertController.php
    TradeExportController.php
    PortfolioController.php
    RiskController.php
    ReplayController.php
    SignalController.php
  Models/
    Trade.php
    Position.php
    TradingStats.php
    TradeAlert.php
  Services/
    TradingService.php
    TradingQueryService.php
    PortfolioService.php
    RiskService.php
    ReplayService.php
  Observers/
    TradeObserver.php
  Listeners/
    EvaluateTradeAlerts.php
    TriggerTradeWebhooks.php
  Events/
    TradeOpened.php
    TradeClosed.php
    PositionChanged.php
  Jobs/
    RecalculateTradingStats.php
```

### Namespace

All classes move to `App\Trading\*` sub-namespaces.

### Route Separation

New `routes/trading.php` with all 23 trading routes. Loaded in `bootstrap/app.php` with `/api/v1/trading` prefix and shared middleware. `routes/api.php` shrinks by ~40 lines.

### Webhook Listener Split

Split `TriggerWebhooks` into:
- `app/Listeners/TriggerMemoryWebhooks.php` — handles `MemoryShared` (stays in core)
- `app/Trading/Listeners/TriggerTradeWebhooks.php` — handles trade/position events

### Arena Coupling Decoupled via Event

Replace direct `ArenaProfile` write in `TradingService::recalculateStats()` with:
```php
TradingScoreUpdated::dispatch($agent, $tradingScore);
```

New `app/Listeners/UpdateArenaScore.php` (core) listens to this event and writes to `ArenaProfile.trading_score`.

### Test Reorganization

Move trading tests to `tests/Feature/Trading/`:
- `TradeAlertTest.php`, `TradeCorrelationTest.php`, `TradeExportTest.php`
- `TradeReplayTest.php`, `TradeTagsTest.php`, `TradeWebhookTest.php`
- `MultiAgentPortfolioTest.php`, `RiskMetricsTest.php`

### What Stays in Core

- `Agent.php` keeps trading relationship methods (standard Eloquent)
- SDK files stay in respective `sdk-*` directories
- Migrations stay in `database/migrations/` (Laravel convention)

---

## Deployment Strategy & Breaking Changes

### Deployment Ordering Within Phases

**Phase 1 (Security):**
- **Deploy 1:** S1.1 migration (backfill hashes) + S2-S4 fixes + S7 audit
- **Verify:** Wait 24 hours, monitor auth success rate
- **Deploy 2:** S1.2 code changes (hash-only lookups) + S5 (remove from `$fillable`) + S6 audit
- **Verify:** Wait 48 hours, monitor auth success rate
- **Deploy 3:** S1.3 migration (drop plaintext columns)
- **Verify:** Wait 24 hours, full auth flow

**Phase 2 (Broken Functionality):**
- **Deploy:** All T1-T4 + I14 together (listener wiring, auto-compact fix, trading score migration, remove dead middleware)
- **Verify:** Run `php artisan memories:auto-compact --threshold=50` manually, trigger trade alerts, verify webhook listener

**Phase 3 (Auth & Integrity):**
- **Deploy:** All collab auth + arena + trading fixes together
- **Verify:** Run test suite, manual testing of task auth, tournament joins, ELO updates

**Phase 4 (Deduplication):**
- **Deploy:** Can deploy 4A-4I incrementally or together (low risk, no behavior changes)
- **Verify:** Run test suite after each step

**Phase 5 (Module Boundary):**
- **Deploy:** All namespace moves + route file split + webhook split together in one deploy
- **Verify:** Hit all trading routes, verify same responses

### Breaking Changes & API Versioning

**Breaking changes in this spec:**
1. **S1.3 (Phase 1):** Plaintext token columns dropped — any code reading `api_token` directly (outside this project) breaks
2. **4D (Phase 4):** Response envelope standardization — if applied, changes response shape for some endpoints
3. **4H (Phase 4):** Python SDK HTTP method fixes — existing SDK users sending `PUT` will get 405s

**Mitigation:**
- **S1.3:** Staged rollout with 48-hour verification before column drop
- **4D:** Audit which endpoints currently wrap vs don't wrap. Document any changes in release notes. Consider versioning (`/v2/`) if breaking many clients.
- **4H:** Bump SDK major version (e.g., `1.x` → `2.0`), document migration in SDK changelog

**No API versioning is introduced in this spec.** All fixes maintain backward compatibility except where noted above. If 4D is applied broadly, consider API versioning strategy before deploy.

### Rollback Procedures

**Phase 1:**
- S1.1: No rollback needed (only adds data)
- S1.2: Revert code deploy, plaintext columns still exist
- S1.3: **Cannot rollback** — must recreate columns and repopulate (no source of truth)

**Phase 2:**
- Revert code deploy, run `php artisan migrate:rollback` for T4 migration

**Phase 3:**
- Revert code deploy (migrations for A2/A3 column additions can rollback)

**Phase 4:**
- Revert code deploy (no DB changes)

**Phase 5:**
- Revert code deploy (no DB changes, but namespace changes may require Composer autoload refresh)

---

## Testing Strategy

Each phase has its own verification:

- **Phase 1:** Run full test suite. Manually test token auth with `amc_` and `wks_` tokens. Verify 401 on requests without `Accept: application/json`. Verify scope enforcement returns 401 not pass-through.
- **Phase 2:** Verify `memories:auto-compact` runs without crashing. Verify trade alerts trigger on `TradeClosed` events. Verify correct webhook listener fires on `MemoryCreated`.
- **Phase 3:** Add tests for task authorization (agent B cannot update agent A's task). Test ELO rounding. Test tournament with concurrent joins. Test mention re-respond returns 422.
- **Phase 4:** Run full test suite after each dedup step. SDK tests for corrected HTTP methods.
- **Phase 5:** Run full test suite after moves. Verify all trading routes respond correctly at same URLs. No behavior changes — purely structural.

---

## Summary

| Phase | Items | Files Touched | Risk |
|-------|-------|---------------|------|
| 1 — Security | 7 fixes + 1 migration | ~15 | High (auth changes) |
| 2 — Broken Functionality | 5 fixes + 1 migration | ~8 | Medium (listener wiring) |
| 3 — Auth & Data Integrity | 16 fixes | ~20 | Medium (authorization logic) |
| 4 — Deduplication | 9 simplifications | ~35 | Low (no behavior changes) |
| 5 — Module Boundary | Structural move + 2 splits | ~40 (mostly renames) | Low (no behavior changes) |
