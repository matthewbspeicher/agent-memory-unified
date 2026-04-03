# Codebase Hardening — Design Spec

**Date:** 2026-03-16
**Status:** Approved
**Scope:** Fix all issues from full codebase review — security, bugs, architecture, tests

---

## Phase 1: Critical Security Fixes

### 1.1 Cross-tenant auth bypass via memory relations
**File:** `app/Http/Controllers/Api/MemoryController.php:80`
**Fix:** Add custom validation rule that checks `relations.*.id` belongs to the authenticated agent or is accessible via `scopeAccessibleBy`. Apply to both `store` and `update` validation.

### 1.2 Workspace membership not validated on memory store/update
**File:** `app/Http/Controllers/Api/MemoryController.php:71`, `app/Services/MemoryService.php:53`
**Fix:** Add custom validation rule or check in `MemoryService::store()` and `update()` that verifies the agent belongs to the specified workspace before allowing association.

### 1.3 SSRF protection for webhook URLs
**File:** `app/Http/Controllers/Api/WebhookController.php:31`, `app/Jobs/DispatchWebhook.php:53`
**Fix:** Validate that webhook URLs do not resolve to private/internal IP addresses (RFC 1918, loopback, link-local, AWS metadata 169.254.169.254). Add DNS resolution check before dispatching.

### 1.4 SQL interpolation in scopeNotExpired
**File:** `app/Models/Memory.php:83`
**Fix:** Replace `whereRaw("(expires_at IS NULL OR expires_at > '{$now}')")` with `where(fn ($q) => $q->whereNull('expires_at')->orWhere('expires_at', '>', now()))`.

### 1.5 Webhook secret leaked in API responses
**File:** `app/Models/WebhookSubscription.php`
**Fix:** Add `protected $hidden = ['secret', 'embedding'];`. Use `makeVisible('secret')` only in the `store()` response.

### 1.6 Revert EmbeddingService to OpenAI
**File:** `app/Services/EmbeddingService.php`
**Fix:** Replace Gemini API calls with OpenAI `text-embedding-3-small`. Use `Authorization: Bearer` header. Keep the content-hash caching. Update `config/services.php` to remove gemini key. Update migration comment.

---

## Phase 2: Token Hashing (Dual-Read Migration)

### 2.1 Add hashed token columns
**Migration:** Add `api_token_hash` to `users`, `token_hash` to `agents`, `api_token_hash` to `workspaces`.

### 2.2 Backfill hashes
**Migration:** Hash all existing plaintext tokens using `hash('sha256', $token)` and store in new columns.

### 2.3 Update auth to check hashed first
**Files:** `AuthenticateAgent.php`, `AgentController.php`, `MagicLinkController.php`
**Pattern:** On lookup, hash the incoming token and query `WHERE token_hash = ?`. Fall back to plaintext column if no match (for tokens created between migration and deploy). New tokens always write both columns.

### 2.4 Hash magic link tokens
**File:** `app/Models/User.php`
**Fix:** Store `hash('sha256', $token)` in `magic_link_token`. Use `hash_equals()` for comparison in `hasValidMagicLink()`. Query by hashed value in `MagicLinkController::verifyLink()`.

---

## Phase 3: Bug Fixes

### 3.1 Webhook signature — send raw JSON body
**File:** `app/Jobs/DispatchWebhook.php:44-53`
**Fix:** Use `Http::withBody($jsonBody, 'application/json')` instead of `Http::post($url, $body)`.

### 3.2 Stale failure_count after increment
**File:** `app/Jobs/DispatchWebhook.php:71-73`
**Fix:** Call `$this->subscription->refresh()` after `increment()`, or compute new count before the update.

### 3.3 Broken cursor pagination in commonsIndex
**File:** `app/Http/Controllers/Api/MemoryController.php:307,320`
**Fix:** Pass `$cursor` to `getCommonsData()` and use it in the query.

### 3.4 to_tsquery injection
**File:** `app/Models/Memory.php:154`
**Fix:** Replace `to_tsquery('english', ?)` with `websearch_to_tsquery('english', ?)`.

### 3.5 DB transactions in MemoryService
**File:** `app/Services/MemoryService.php`
**Fix:** Wrap `store()` and `update()` in `DB::transaction()`.

### 3.6 TOCTOU quota race
**File:** `app/Services/MemoryService.php:25-28`
**Fix:** Use `SELECT ... FOR UPDATE` on the agent row within the transaction to serialize concurrent quota checks.

### 3.7 Make TriggerWebhooks queued
**File:** `app/Listeners/TriggerWebhooks.php`
**Fix:** Add `implements ShouldQueue`.

### 3.8 Leaderboard query limit
**File:** `app/Http/Controllers/LeaderboardController.php:13-24`
**Fix:** Push score calculation to SQL `ORDER BY` and add `->limit(200)` before `->get()`.

### 3.9 Compact error message leak
**File:** `app/Http/Controllers/Api/MemoryController.php:235`
**Fix:** Log the exception, return generic error message.

### 3.10 N+1 in DashboardController
**File:** `app/Http/Controllers/Auth/DashboardController.php:16-23`
**Fix:** Single query with `withCount('memories')`, derive all stats from that collection.

### 3.11 LIKE wildcard injection in MemoryBrowser
**File:** `app/Http/Controllers/MemoryBrowserController.php:23-26`
**Fix:** Escape `%` and `_` in search input before LIKE.

### 3.12 SSE stream route — update CLAUDE.md
**File:** `routes/api.php:28-29`, `CLAUDE.md`
**Fix:** Document that SSE was replaced by polling due to FrankenPHP/Octane worker exhaustion.

---

## Phase 4: Architecture Improvements

### 4.1 Extract Form Requests
Create `StoreMemoryRequest`, `UpdateMemoryRequest`, `CompactMemoryRequest`, `RegisterAgentRequest`, `StoreWebhookRequest`. Move validation + workspace/relation authorization rules into these.

### 4.2 Replace resolveAgent() with middleware
Move workspace-token agent resolution into the `AuthenticateAgent` middleware. Set resolved agent on `$request->attributes`. Eliminate the 6 repeated `if ($agent instanceof JsonResponse)` blocks.

### 4.3 Replace FormatsMemories with API Resource
Create `MemoryResource` and `MemoryCollection`. Use `whenLoaded('agent')` for conditional agent inclusion in commons responses.

### 4.4 Move getCommonsData to MemoryService
Add `MemoryService::listCommons()` to mirror `searchCommons()`. Remove private controller method.

### 4.5 Move billing enforcement out of auth middleware
Extract `enforceSoftLock()` from `AuthenticateAgent` into a separate `EnforcePlanLimits` middleware.

---

## Phase 5: Comprehensive Tests (~40+ new tests)

### 5.1 MCP Tool Tests
- Store, Get, Update, Delete happy paths
- Search with type/tag filters
- Share memory
- Error cases (missing key, empty payload)

### 5.2 IDOR / Cross-Tenant Tests
- Agent B cannot read/update/delete Agent A's memory
- Agent B cannot create relations to Agent A's private memories
- Agent B cannot delete Agent A's webhook
- Agent B cannot store memory in workspace it doesn't belong to

### 5.3 Untested Endpoint Tests
- `POST /webhooks/{id}/test`
- `GET /commons/poll` (with and without `since` parameter)
- `GET /agents/{id}` response structure + 404

### 5.4 Command Tests
- `memories:prune` — creates expired + non-expired, asserts only expired deleted
- `app:create-owner` — happy path + duplicate email
- `app:register-agent` — happy path + invalid token

### 5.5 Error Path Tests
- `compact` with < 2 memories → 422
- `compact` with summarization failure → 500
- Webhook test for non-owned webhook → 404

### 5.6 Workspace Token Auth Tests
- Missing `agent_id` → 422
- Agent not found → 404
- Agent not in workspace → 403
- Happy path → success

### 5.7 Refactor CommonsStreamTest
- Remove skipped SSE tests
- Convert to CommonsPollTest with real assertions

---

## Key Design Decisions

- **Dual-read token migration** over one-shot: avoids downtime, allows gradual rollout
- **`websearch_to_tsquery`** over `plainto_tsquery`: supports quoted phrases and negation, better UX
- **Form Requests** over inline validation: testable, reusable, reduces controller size by ~100 lines
- **MemoryResource** over trait: standard Laravel pattern, conditional field inclusion, pagination support
- **Separate EnforcePlanLimits middleware** over in-auth: single responsibility, testable independently
