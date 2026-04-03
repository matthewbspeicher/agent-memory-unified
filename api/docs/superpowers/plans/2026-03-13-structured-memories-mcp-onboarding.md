# Structured Memory Types + MCP One-Liner Onboarding — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class `type` enum to memories, update all surfaces (API, MCP, SDKs, UI), seed the commons with curated developer knowledge, and polish MCP onboarding to a one-liner.

**Architecture:** Add a `type VARCHAR(20) DEFAULT 'note'` column to the memories table. Propagate the type through validation, service, response formatting, MCP tools (Node.js + Laravel), both SDKs, and the landing page. Replace the existing commons seeder with curated typed content. Rewrite skill.md as the canonical agent onboarding doc.

**Tech Stack:** Laravel 12 / PHP 8.3 / PostgreSQL + pgvector / Node.js MCP server / TypeScript SDK / Vue 3 + Inertia

**Spec:** `docs/superpowers/specs/2026-03-13-structured-memories-mcp-onboarding-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `database/migrations/XXXX_add_type_to_memories_table.php` | Add type column + index (may already exist — verify first) |
| `database/seeders/CommonsSeeder.php` | Create "Remembr" system agent + 40 typed public memories |
| `app/Console/Commands/EmbedMissingMemories.php` | Backfill null embeddings in batches |
| `tests/Feature/CommonsSeederTest.php` | Seeder creates agent + memories, idempotent |
| `tests/Feature/EmbedMissingCommandTest.php` | Command processes memories without embeddings |

### Modified Files
| File | Change |
|------|--------|
| `app/Models/Memory.php` | Add `TYPES` constant (type may already be in $fillable) |
| `app/Http/Controllers/Api/MemoryController.php` | Type validation on store/update, type filter on search/list/commons |
| `app/Services/MemoryService.php` | Type in store attributes, type filter in search/list signatures |
| `app/Concerns/FormatsMemories.php` | Add `'type' => $memory->type` to response array |
| `mcp-server/index.js` | Add type enum to store/update/search tool schemas |
| `mcp-server/package.json` | Add `"package.json"` to files array |
| `app/Mcp/Tools/StoreMemoryTool.php` | Add type parameter with enum |
| `app/Mcp/Tools/SearchMemoriesTool.php` | Add type filter parameter |
| `app/Mcp/Tools/SearchCommonsTool.php` | Add type filter parameter |
| `app/Mcp/Tools/ListMemoriesTool.php` | Add type filter parameter |
| `app/Mcp/Tools/UpdateMemoryTool.php` | Add type parameter |
| `sdk/js/src/types.ts` | Add type to Memory, StoreOptions, UpdateOptions, SearchOptions |
| `sdk/js/src/index.ts` | Forward type in remember, update, search, searchCommons |
| `sdk/src/AgentMemoryClient.php` | Add type to remember, search, searchCommons |
| `public/skill.md` | Complete rewrite with types, MCP one-liner, all endpoints |
| `resources/js/Pages/Home.vue` | Update curl example with type field |
| `resources/js/Pages/Dashboard.vue` | Add MCP config copy-paste card to agent list |

### Files to Remove
| File | Reason |
|------|--------|
| `app/Console/Commands/SeedCommonsCommand.php` | Replaced by CommonsSeeder |
| `database/seeders/HivemindSeeder.php` | Replaced by CommonsSeeder |

---

## Chunk 1: Memory Type System (Backend)

### Task 1: Fix Existing Migration

The migration `2026_03_13_162900_add_type_to_memories_table.php` already exists but has issues: it uses `VARCHAR(255)` (no size limit), `->after('value')` (PostgreSQL ignores this), and is missing an index. Fix it.

**Files:**
- Modify: `database/migrations/2026_03_13_162900_add_type_to_memories_table.php`

- [ ] **Step 1: Check migration status**

Run: `/opt/homebrew/bin/php artisan migrate:status 2>&1 | grep type`

**If the migration has NOT been run yet:**

- [ ] **Step 2a: Fix the migration file**

Replace the contents of `database/migrations/2026_03_13_162900_add_type_to_memories_table.php` with:

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('memories', function (Blueprint $table) {
            $table->string('type', 20)->default('note');
            $table->index('type');
        });
    }

    public function down(): void
    {
        Schema::table('memories', function (Blueprint $table) {
            $table->dropIndex(['type']);
            $table->dropColumn('type');
        });
    }
};
```

Run: `/opt/homebrew/bin/php artisan migrate`

**If the migration HAS already been run:**

- [ ] **Step 2b: Create a corrective migration**

```bash
/opt/homebrew/bin/php artisan make:migration fix_memories_type_column --table=memories
```

Edit the generated file:

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('memories', function (Blueprint $table) {
            $table->string('type', 20)->default('note')->change();
            $table->index('type');
        });
    }

    public function down(): void
    {
        Schema::table('memories', function (Blueprint $table) {
            $table->dropIndex(['type']);
            $table->string('type')->default('note')->change();
        });
    }
};
```

Run: `/opt/homebrew/bin/php artisan migrate`

- [ ] **Step 3: Commit**

```bash
git add database/migrations/*type*
git commit -m "feat: add type column to memories table with index and VARCHAR(20)"
```

---

### Task 2: Add TYPES Constant to Memory Model

**Files:**
- Modify: `app/Models/Memory.php`

- [ ] **Step 1: Add TYPES constant**

In `app/Models/Memory.php`, add after the class opening brace (around line 14):

```php
const TYPES = [
    'fact', 'preference', 'procedure', 'lesson',
    'error_fix', 'tool_tip', 'context', 'note',
];
```

Verify `'type'` is already in `$fillable`. If not, add it.

- [ ] **Step 2: Add scopeOfType query scope**

In `app/Models/Memory.php`, add alongside the other scope methods (around line 75+):

```php
public function scopeOfType(Builder $query, string $type): Builder
{
    return $query->where('type', $type);
}
```

Ensure `use Illuminate\Database\Eloquent\Builder;` is imported at the top (it likely already is from existing scopes).

- [ ] **Step 3: Commit**

```bash
git add app/Models/Memory.php
git commit -m "feat: add TYPES constant and scopeOfType to Memory model"
```

---

### Task 3: Add Type to Response Formatting

**Files:**
- Modify: `app/Concerns/FormatsMemories.php:23-37`
- Test: `tests/Feature/MemoryApiTest.php`

- [ ] **Step 1: Write the failing test**

Add to `tests/Feature/MemoryApiTest.php`:

```php
it('includes type in memory response', function () {
    $agent = makeAgent(makeOwner());
    $memory = Memory::factory()->create([
        'agent_id' => $agent->id,
        'key' => 'type-test',
        'value' => 'test value',
        'type' => 'fact',
        'visibility' => 'private',
    ]);

    $response = $this->getJson('/api/v1/memories/type-test', withAgent($agent));

    $response->assertOk();
    $response->assertJsonPath('data.type', 'fact');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/php artisan test --filter="includes type in memory response"`
Expected: FAIL — `type` not present in response JSON.

- [ ] **Step 3: Add type to FormatsMemories**

In `app/Concerns/FormatsMemories.php`, in the `formatMemory()` return array (around line 23), add `'type'` after `'value'`:

```php
'type' => $memory->type,
```

The return array should now include:
```php
return [
    'id' => $memory->id,
    'key' => $memory->key,
    'value' => $memory->value,
    'type' => $memory->type,
    'visibility' => $memory->visibility,
    // ... rest unchanged
];
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/php artisan test --filter="includes type in memory response"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/Concerns/FormatsMemories.php tests/Feature/MemoryApiTest.php
git commit -m "feat: include type in memory API responses"
```

---

### Task 4: Add Type Validation to Controller

**Files:**
- Modify: `app/Http/Controllers/Api/MemoryController.php:29-44` (store), `:104-118` (update)
- Test: `tests/Feature/MemoryApiTest.php`

- [ ] **Step 1: Write failing tests**

Add to `tests/Feature/MemoryApiTest.php`:

```php
it('accepts valid memory type on store', function () {
    $agent = makeAgent(makeOwner());
    $response = $this->postJson('/api/v1/memories', [
        'value' => 'PostgreSQL IVFFlat needs >100 rows',
        'type' => 'error_fix',
    ], withAgent($agent));

    $response->assertCreated();
    $response->assertJsonPath('data.type', 'error_fix');
});

it('rejects invalid memory type on store', function () {
    $agent = makeAgent(makeOwner());
    $response = $this->postJson('/api/v1/memories', [
        'value' => 'some value',
        'type' => 'invalid_type',
    ], withAgent($agent));

    $response->assertUnprocessable();
    $response->assertJsonValidationErrors('type');
});

it('defaults to note type when not specified', function () {
    $agent = makeAgent(makeOwner());
    $response = $this->postJson('/api/v1/memories', [
        'value' => 'no type specified',
    ], withAgent($agent));

    $response->assertCreated();
    $response->assertJsonPath('data.type', 'note');
});

it('allows type to be updated', function () {
    $agent = makeAgent(makeOwner());
    $this->postJson('/api/v1/memories', [
        'key' => 'update-type-test',
        'value' => 'original value',
        'type' => 'note',
    ], withAgent($agent));

    $response = $this->patchJson('/api/v1/memories/update-type-test', [
        'type' => 'lesson',
    ], withAgent($agent));

    $response->assertOk();
    $response->assertJsonPath('data.type', 'lesson');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/homebrew/bin/php artisan test --filter="accepts valid memory type|rejects invalid memory type|defaults to note type|allows type to be updated"`
Expected: Some will fail (invalid type accepted, type not in response, etc.)

- [ ] **Step 3: Add validation rules**

In `app/Http/Controllers/Api/MemoryController.php`:

**In `store()` method** (around line 29), add to the validation array:

```php
'type' => ['sometimes', 'string', Rule::in(Memory::TYPES)],
```

Add the import at the top of the file if not present:

```php
use App\Models\Memory;
use Illuminate\Validation\Rule;
```

**In `update()` method** (around line 104), add the same rule:

```php
'type' => ['sometimes', 'string', Rule::in(Memory::TYPES)],
```

- [ ] **Step 4: Add type to MemoryService::store()**

In `app/Services/MemoryService.php`, in the `store()` method, find the `updateOrCreate` call (around lines 42-57). Add `'type'` to the attributes array:

```php
'type' => $data['type'] ?? 'note',
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/opt/homebrew/bin/php artisan test --filter="accepts valid memory type|rejects invalid memory type|defaults to note type|allows type to be updated"`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add app/Http/Controllers/Api/MemoryController.php app/Services/MemoryService.php tests/Feature/MemoryApiTest.php
git commit -m "feat: validate and persist memory type on store/update"
```

---

### Task 5: Add Type Filter to Search and List

**Files:**
- Modify: `app/Services/MemoryService.php:145-158` (listForAgent), `:164-201` (searchForAgent), `:203-240` (searchCommons)
- Modify: `app/Http/Controllers/Api/MemoryController.php:73-88` (index), `:195-220` (search), `:227-249` (commonsIndex), `:288-318` (commonsSearch)
- Test: `tests/Feature/MemoryApiTest.php`

- [ ] **Step 1: Write failing tests**

Add to `tests/Feature/MemoryApiTest.php`:

```php
it('filters memories by type in list endpoint', function () {
    $agent = makeAgent(makeOwner());
    Memory::factory()->create([
        'agent_id' => $agent->id,
        'key' => 'fact-mem',
        'value' => 'a fact',
        'type' => 'fact',
    ]);
    Memory::factory()->create([
        'agent_id' => $agent->id,
        'key' => 'lesson-mem',
        'value' => 'a lesson',
        'type' => 'lesson',
    ]);

    $response = $this->getJson('/api/v1/memories?type=fact', withAgent($agent));

    $response->assertOk();
    $response->assertJsonCount(1, 'data');
    $response->assertJsonPath('data.0.type', 'fact');
});

it('filters memories by type in search endpoint', function () {
    $agent = makeAgent(makeOwner());
    Memory::factory()->create([
        'agent_id' => $agent->id,
        'value' => 'PostgreSQL error fix for booleans',
        'type' => 'error_fix',
        'embedding' => array_fill(0, 1536, 0.1),
    ]);
    Memory::factory()->create([
        'agent_id' => $agent->id,
        'value' => 'PostgreSQL is a great database',
        'type' => 'fact',
        'embedding' => array_fill(0, 1536, 0.1),
    ]);

    $response = $this->getJson('/api/v1/memories/search?q=postgresql&type=error_fix', withAgent($agent));

    $response->assertOk();
    collect($response->json('data'))->each(fn ($m) => expect($m['type'])->toBe('error_fix'));
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/homebrew/bin/php artisan test --filter="filters memories by type"`
Expected: FAIL — type filter not applied.

- [ ] **Step 3: Update MemoryService method signatures**

In `app/Services/MemoryService.php`:

**`listForAgent()`** (around line 145) — add `?string $type = null` parameter:
```php
public function listForAgent(Agent $agent, int $perPage = 20, array $tags = [], ?string $type = null): LengthAwarePaginator
```

Add type filter to the query chain:
```php
->when($type, fn ($query) => $query->where('type', $type))
```

**`searchForAgent()`** (around line 164) — add `?string $type = null` parameter:
```php
public function searchForAgent(Agent $agent, string $q, int $limit = 10, array $tags = [], ?string $type = null): array
```

Add type filter to BOTH the vector search query AND the keyword search query inside this method. Find the `semanticSearch` query builder chain and add:
```php
->when($type, fn ($query) => $query->where('type', $type))
```

Do the same for the `keywordSearch` query.

**`searchCommons()`** (around line 203) — same pattern:
```php
public function searchCommons(Agent $agent, string $q, int $limit = 10, array $tags = [], ?string $type = null): array
```

Add `->when($type, fn ($query) => $query->where('type', $type))` to both search queries.

- [ ] **Step 4: Update Controller to pass type parameter**

In `app/Http/Controllers/Api/MemoryController.php`:

**`index()`** (around line 73):
```php
$type = $request->query('type');
// Pass $type to listForAgent
$memories = $this->memories->listForAgent($agent, 20, $tags, $type);
```

**`search()`** (around line 195):
```php
$type = $request->query('type');
// Pass $type to searchForAgent
$results = $this->memories->searchForAgent($agent, $q, $limit, $tags, $type);
```

**`commonsIndex()`** (around line 227):
Add type parameter. When type is provided, bypass the cache (same as tags):
```php
$type = $request->query('type');
```
Update the cache-bypass condition (around line 240) to also skip when `$type` is present:
```php
if ($cursor === null && $limit === 10 && empty($tags) && $type === null) {
```
Pass `$type` to `getCommonsData()`:
```php
return response()->json($this->getCommonsData($limit, $tags, $type));
```
Also update the cached call to pass null: `$this->getCommonsData($limit, [], null)`

**`getCommonsData()`** (around line 251):
Add `?string $type = null` parameter and apply the filter:
```php
private function getCommonsData(int $limit, array $tags = [], ?string $type = null): array
{
    $query = Memory::query()
        ->public()
        ->notExpired()
        ->latest()
        ->with('agent:id,name,description');

    if (! empty($tags)) {
        $query->withTags($tags);
    }

    if ($type) {
        $query->where('type', $type);
    }

    // ... rest unchanged
```

**`commonsSearch()`** (around line 288):
```php
$type = $request->query('type');
// Pass to searchCommons
$results = $this->memories->searchCommons($agent, $q, $limit, $tags, $type);
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/opt/homebrew/bin/php artisan test --filter="filters memories by type"`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `/opt/homebrew/bin/php artisan test`
Expected: All tests pass (no regressions).

- [ ] **Step 7: Commit**

```bash
git add app/Services/MemoryService.php app/Http/Controllers/Api/MemoryController.php tests/Feature/MemoryApiTest.php
git commit -m "feat: add type filter to memory search and list endpoints"
```

---

## Chunk 2: MCP Tools Update

### Task 6: Update Node.js MCP Server Tool Schemas

**Files:**
- Modify: `mcp-server/index.js:54-76` (store_memory), `:78-106` (update_memory), `:108-121` (search_memories), `:136-147` (list_memories), `:162-174` (search_commons)

- [ ] **Step 1: Add type to store_memory tool**

In `mcp-server/index.js`, find the `store_memory` tool definition (around line 54). Add to `inputSchema.properties`:

```javascript
type: {
  type: 'string',
  enum: ['fact', 'preference', 'procedure', 'lesson', 'error_fix', 'tool_tip', 'context', 'note'],
  description: 'Memory type. fact=objective knowledge, preference=user/agent prefs, procedure=how-to steps, lesson=experiential learning, error_fix=problem+solution, tool_tip=API/tool patterns, context=session state, note=general (default)',
  default: 'note',
},
```

In the handler for `store_memory`, add `type` to the destructured params and add a conditional body assignment (matching the existing `if (key) body.key = key;` pattern):

```javascript
// Add to destructured params: ..., tags, type }) => {
// Add after existing `if (tags) body.tags = tags;`:
if (type) body.type = type;
```

- [ ] **Step 2: Add type to update_memory tool**

Same pattern — add `type` to the Zod schema properties with the same enum. In the handler, add `if (type) body.type = type;` (matching the conditional body pattern).

- [ ] **Step 3: Add type filter to search_memories tool**

Add to `inputSchema.properties`:

```javascript
type: {
  type: 'string',
  enum: ['fact', 'preference', 'procedure', 'lesson', 'error_fix', 'tool_tip', 'context', 'note'],
  description: 'Filter results to this memory type only',
},
```

In the handler, add `type` to the query string (match existing template literal pattern):

```javascript
const typeParam = type ? `&type=${encodeURIComponent(type)}` : '';
const result = await api("GET", `/memories/search?q=${encodeURIComponent(q)}&limit=${limit}${tagsParam}${typeParam}`);
```

- [ ] **Step 4: Add type filter to list_memories tool**

Same pattern as search — add `type` to schema, add to query params.

- [ ] **Step 5: Add type filter to search_commons tool**

Same pattern — add `type` to schema and query params.

- [ ] **Step 6: Verify MCP server starts**

Run: `cd /opt/homebrew/var/www/agent-memory/mcp-server && node -c index.js`
Expected: No syntax errors.

- [ ] **Step 7: Commit**

```bash
git add mcp-server/index.js
git commit -m "feat: add type enum to MCP server tool schemas"
```

---

### Task 7: Update Laravel MCP Tools

**Files:**
- Modify: `app/Mcp/Tools/StoreMemoryTool.php:21-32`
- Modify: `app/Mcp/Tools/UpdateMemoryTool.php:21-32`
- Modify: `app/Mcp/Tools/SearchMemoriesTool.php:21-28`
- Modify: `app/Mcp/Tools/SearchCommonsTool.php:21-28`
- Modify: `app/Mcp/Tools/ListMemoriesTool.php:21-27`

- [ ] **Step 1: Add type to StoreMemoryTool schema**

In `app/Mcp/Tools/StoreMemoryTool.php`, add to the schema definition:

```php
'type' => [
    'type' => 'string',
    'enum' => Memory::TYPES,
    'description' => 'Memory type: fact, preference, procedure, lesson, error_fix, tool_tip, context, note',
    'default' => 'note',
],
```

Add `use App\Models\Memory;` import if not present.

In the `handle()` method, include `'type'` in the data array passed to `$this->memories->store()`.

- [ ] **Step 2: Add type to UpdateMemoryTool schema**

Same enum property. Include `'type'` in the update data array.

- [ ] **Step 3: Add type filter to SearchMemoriesTool**

Add to schema:

```php
'type' => [
    'type' => 'string',
    'enum' => Memory::TYPES,
    'description' => 'Filter results to this memory type',
],
```

In `handle()`, extract type from input and pass to `searchForAgent()`.

- [ ] **Step 4: Add type filter to SearchCommonsTool**

Same pattern as SearchMemoriesTool.

- [ ] **Step 5: Add type filter to ListMemoriesTool**

Same pattern — add to schema, pass to `listForAgent()`.

- [ ] **Step 6: Run test suite to verify no regressions**

Run: `/opt/homebrew/bin/php artisan test`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/Mcp/Tools/
git commit -m "feat: add type parameter to Laravel MCP tools"
```

---

## Chunk 3: SDK Updates

### Task 8: Update JS/TS SDK Types

**Files:**
- Modify: `sdk/js/src/types.ts`

- [ ] **Step 1: Add MemoryType union type**

At the top of `sdk/js/src/types.ts` (before the Memory interface), add:

```typescript
export type MemoryType = 'fact' | 'preference' | 'procedure' | 'lesson' | 'error_fix' | 'tool_tip' | 'context' | 'note';
```

- [ ] **Step 2: Add type to Memory interface**

In the `Memory` interface (around line 1-14), add after `value`:

```typescript
type: MemoryType;
```

- [ ] **Step 3: Add type to StoreOptions**

In `StoreOptions` (around line 20-31), add:

```typescript
type?: MemoryType;
```

- [ ] **Step 4: Add type to UpdateOptions**

In `UpdateOptions` (around line 33-41), add:

```typescript
type?: MemoryType;
```

- [ ] **Step 5: Add type to SearchOptions**

In `SearchOptions` (around line 43-46), add:

```typescript
type?: MemoryType;
```

- [ ] **Step 6: Commit**

```bash
git add sdk/js/src/types.ts
git commit -m "feat: add MemoryType to JS SDK type definitions"
```

---

### Task 9: Update JS/TS SDK Client Methods

**Files:**
- Modify: `sdk/js/src/index.ts:90-92` (remember), `:98-100` (update), `:126-132` (search), `:134-140` (searchCommons)

- [ ] **Step 1: Update remember() to forward type**

The `remember()` method (around line 90) already spreads `StoreOptions` into the request body. Since `type` is now in `StoreOptions`, it will be forwarded automatically. Verify this — the method should look like:

```typescript
async remember(value: string, options?: StoreOptions): Promise<Memory> {
    return this.request<Memory>('POST', '/memories', { value, ...options });
}
```

If it doesn't spread options, update it.

- [ ] **Step 2: Update search() to forward type**

In `search()` (around line 126), add `type` to the query params:

```typescript
async search(query: string, options?: SearchOptions): Promise<MemorySearchResult[]> {
    const params = new URLSearchParams({ q: query });
    if (options?.limit) params.set('limit', String(options.limit));
    if (options?.tags?.length) params.set('tags', options.tags.join(','));
    if (options?.type) params.set('type', options.type);
    const res = await this.request<{ data: MemorySearchResult[] }>('GET', `/memories/search?${params}`);
    return res.data;
}
```

- [ ] **Step 3: Update searchCommons() to forward type**

Same pattern as `search()` — add type to query params:

```typescript
if (options?.type) params.set('type', options.type);
```

- [ ] **Step 4: Verify SDK compiles**

Run: `cd /opt/homebrew/var/www/agent-memory/sdk/js && /Users/mspeicher/.nvm/versions/node/v22.22.0/bin/npx tsc --noEmit`
Expected: No type errors.

- [ ] **Step 5: Commit**

```bash
git add sdk/js/src/index.ts
git commit -m "feat: forward type parameter in JS SDK methods"
```

---

### Task 10: Update PHP SDK

**Files:**
- Modify: `sdk/src/AgentMemoryClient.php:65-68` (remember), `:126-134` (search), `:139-147` (searchCommons)

- [ ] **Step 1: Verify remember() already forwards type**

The `remember()` method (line 65) takes an array `$data` and POSTs it. Since it's a pass-through, `type` in the array will be forwarded automatically. Verify:

```php
public function remember(array $data): array
{
    return $this->client->post('memories', $data)->json('data');
}
```

If this already passes the full array, no change needed for store.

- [ ] **Step 2: Add type to search()**

In `search()` (around line 126), add type to query params:

```php
public function search(string $query, int $limit = 10, array $tags = [], ?string $type = null): array
{
    $params = ['q' => $query, 'limit' => $limit];
    if ($tags) $params['tags'] = implode(',', $tags);
    if ($type) $params['type'] = $type;
    return $this->client->get('memories/search', $params)->json('data');
}
```

- [ ] **Step 3: Add type to searchCommons()**

Same pattern:

```php
public function searchCommons(string $query, int $limit = 10, array $tags = [], ?string $type = null): array
{
    $params = ['q' => $query, 'limit' => $limit];
    if ($tags) $params['tags'] = implode(',', $tags);
    if ($type) $params['type'] = $type;
    return $this->client->get('commons/search', $params)->json('data');
}
```

- [ ] **Step 4: Add type docblocks**

Update the docblocks on `remember()`, `search()`, and `searchCommons()` to document the type parameter and valid values.

- [ ] **Step 5: Commit**

```bash
git add sdk/src/AgentMemoryClient.php
git commit -m "feat: add type parameter to PHP SDK search methods"
```

---

## Chunk 4: skill.md Rewrite + MCP Package Polish

### Task 11: Rewrite skill.md

**Files:**
- Modify: `public/skill.md` (complete rewrite)

- [ ] **Step 1: Write new skill.md**

Replace the entire contents of `public/skill.md` with a comprehensive document covering:

1. **What is Remembr** — one paragraph
2. **Quick Setup (MCP)** — the one-liner config for Claude Desktop, Claude Code, Cursor
3. **Memory Types** — table of all 8 types with when-to-use guidance
4. **API Reference** — all endpoints with curl examples:
   - Register agent (POST /v1/agents/register)
   - Store memory (POST /v1/memories) — with type, tags, importance, confidence, ttl
   - Get by key (GET /v1/memories/{key})
   - List memories (GET /v1/memories?type=&tags=)
   - Update (PATCH /v1/memories/{key})
   - Delete (DELETE /v1/memories/{key})
   - Search own memories (GET /v1/memories/search?q=&type=)
   - Search commons (GET /v1/commons/search?q=&type=)
   - Share (POST /v1/memories/{key}/share)
   - Workspaces (GET/POST /v1/workspaces)
   - Memory relations (via store/update `relations` field)
5. **Best Practices** — when to use each type, importance/confidence guidelines, tagging conventions
6. **Memory Object Shape** — complete JSON example with ALL fields including type

The document should be ~200-300 lines, focused and practical. No fluff.

- [ ] **Step 2: Verify it's served correctly**

Run: `curl -s http://localhost:8000/skill.md | head -5`
Expected: Returns the new skill.md content with `Content-Type: text/markdown`.

- [ ] **Step 3: Commit**

```bash
git add public/skill.md
git commit -m "docs: rewrite skill.md with types, MCP setup, and full API reference"
```

---

### Task 12: Polish MCP Package for npm

**Files:**
- Modify: `mcp-server/package.json`
- Modify: `mcp-server/README.md` (rewrite)

- [ ] **Step 1: Update package.json files array**

In `mcp-server/package.json`, find the `"files"` array and add `"package.json"` if missing:

```json
"files": ["index.js", "package.json", "README.md"],
```

- [ ] **Step 2: Rewrite README.md**

Replace `mcp-server/README.md` with a concise setup guide:

- Package name and description
- One-liner config for Claude Desktop
- One-liner for Claude Code: `claude mcp add remembr -- npx -y @remembr/mcp-server`
- Environment variables table (REMEMBR_AGENT_TOKEN required, REMEMBR_BASE_URL optional)
- Link to full docs at remembr.dev/docs
- Available tools list (one line each)

- [ ] **Step 3: Commit**

```bash
git add mcp-server/package.json mcp-server/README.md
git commit -m "feat: polish MCP package for npm publishing"
```

---

## Chunk 5: Commons Seeder + Embed Missing Command

### Task 13: Create EmbedMissingMemories Command

**Files:**
- Create: `app/Console/Commands/EmbedMissingMemories.php`
- Create: `tests/Feature/EmbedMissingCommandTest.php`

- [ ] **Step 1: Write failing test**

Create `tests/Feature/EmbedMissingCommandTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->owner = User::factory()->create(['api_token' => 'embed_test_owner']);
    $this->agent = Agent::factory()->create([
        'owner_id' => $this->owner->id,
        'api_token' => 'amc_embed_test',
    ]);
});

it('embeds memories that are missing embeddings', function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embedBatch')
            ->once()
            ->andReturn([array_fill(0, 1536, 0.5)]);
    });

    Memory::factory()->create([
        'agent_id' => $this->agent->id,
        'value' => 'needs embedding',
        'embedding' => null,
    ]);

    $this->artisan('memories:embed-missing')
        ->assertExitCode(0);

    $memory = Memory::first();
    expect($memory->embedding)->not->toBeNull();
});

it('skips memories that already have embeddings', function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldNotReceive('embedBatch');
    });

    Memory::factory()->create([
        'agent_id' => $this->agent->id,
        'value' => 'already embedded',
        'embedding' => array_fill(0, 1536, 0.1),
    ]);

    $this->artisan('memories:embed-missing')
        ->assertExitCode(0);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/homebrew/bin/php artisan test tests/Feature/EmbedMissingCommandTest.php`
Expected: FAIL — command not found.

- [ ] **Step 3: Create the command**

Create `app/Console/Commands/EmbedMissingMemories.php`:

```php
<?php

namespace App\Console\Commands;

use App\Models\Memory;
use App\Services\EmbeddingService;
use Illuminate\Console\Command;

class EmbedMissingMemories extends Command
{
    protected $signature = 'memories:embed-missing {--batch=50 : Batch size}';
    protected $description = 'Generate embeddings for memories that are missing them';

    public function handle(EmbeddingService $embeddings): int
    {
        $batchSize = (int) $this->option('batch');
        $total = Memory::whereNull('embedding')->count();

        if ($total === 0) {
            $this->info('No memories missing embeddings.');
            return 0;
        }

        $this->info("Found {$total} memories missing embeddings. Processing in batches of {$batchSize}...");
        $processed = 0;

        Memory::whereNull('embedding')
            ->chunkById($batchSize, function ($memories) use ($embeddings, &$processed) {
                $values = $memories->pluck('value')->toArray();
                $vectors = $embeddings->embedBatch($values);

                foreach ($memories as $i => $memory) {
                    if (isset($vectors[$i])) {
                        $memory->update(['embedding' => $vectors[$i]]);
                        $processed++;
                    }
                }

                $this->info("  Processed {$processed} memories...");
            });

        $this->info("Done. Embedded {$processed} memories.");
        return 0;
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/opt/homebrew/bin/php artisan test tests/Feature/EmbedMissingCommandTest.php`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/Console/Commands/EmbedMissingMemories.php tests/Feature/EmbedMissingCommandTest.php
git commit -m "feat: add memories:embed-missing artisan command"
```

---

### Task 14: Create Commons Seeder

**Files:**
- Create: `database/seeders/CommonsSeeder.php`
- Create: `tests/Feature/CommonsSeederTest.php`
- Remove: `app/Console/Commands/SeedCommonsCommand.php`

- [ ] **Step 1: Write failing test**

Create `tests/Feature/CommonsSeederTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\Memory;
use Database\Seeders\CommonsSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

it('creates the Remembr system agent', function () {
    $this->seed(CommonsSeeder::class);

    $agent = Agent::where('name', 'Remembr')->first();
    expect($agent)->not->toBeNull();
    expect($agent->description)->toBe('Curated developer knowledge');
});

it('creates typed public memories', function () {
    $this->seed(CommonsSeeder::class);

    $agent = Agent::where('name', 'Remembr')->first();
    $memories = Memory::where('agent_id', $agent->id)->get();

    expect($memories)->toHaveCount(40);
    expect($memories->where('visibility', 'public'))->toHaveCount(40);

    // Verify type distribution
    expect($memories->where('type', 'error_fix')->count())->toBe(10);
    expect($memories->where('type', 'tool_tip')->count())->toBe(10);
    expect($memories->where('type', 'procedure')->count())->toBe(8);
    expect($memories->where('type', 'fact')->count())->toBe(7);
    expect($memories->where('type', 'lesson')->count())->toBe(5);
});

it('is idempotent', function () {
    $this->seed(CommonsSeeder::class);
    $this->seed(CommonsSeeder::class);

    expect(Agent::where('name', 'Remembr')->count())->toBe(1);
    expect(Memory::where('agent_id', Agent::where('name', 'Remembr')->first()->id)->count())->toBe(40);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/homebrew/bin/php artisan test tests/Feature/CommonsSeederTest.php`
Expected: FAIL — seeder class not found.

- [ ] **Step 3: Create CommonsSeeder**

Create `database/seeders/CommonsSeeder.php` with the full 40 memories as defined in the spec (Section 4.2). The seeder should:

1. Create or find the "Remembr" agent (use `firstOrCreate` with name)
2. For each memory, use `firstOrCreate` with `['agent_id' => $agent->id, 'key' => $key]` to be idempotent
3. Set `visibility: 'public'`, `confidence: 1.0`, `importance: 7-9` (varies), proper `type` and `tags`
4. Leave `embedding` as null (handled by `memories:embed-missing`)
5. Print instructions: "Run `php artisan memories:embed-missing` to generate embeddings"

**Owner user:** Agents require an `owner_id` (foreign key to users). Create a system user first (same pattern as HivemindSeeder):

```php
$systemUser = User::firstOrCreate(
    ['email' => 'system@remembr.dev'],
    [
        'name' => 'Remembr System',
        'password' => bcrypt(Str::random(16)),
        'api_token' => 'system_' . Str::random(40),
    ]
);

$agent = Agent::firstOrCreate(
    ['name' => 'Remembr'],
    [
        'owner_id' => $systemUser->id,
        'description' => 'Curated developer knowledge',
        'api_token' => 'amc_system_' . Str::random(40),
    ]
);
```

The seed data array should contain all 40 items from the spec:
- 10 error_fix memories
- 10 tool_tip memories
- 8 procedure memories
- 7 fact memories
- 5 lesson memories

Each memory needs: `key` (slug), `value` (the knowledge), `type`, `tags` (array), `importance` (7-9), `visibility` ('public').

- [ ] **Step 4: Run tests to verify they pass**

Run: `/opt/homebrew/bin/php artisan test tests/Feature/CommonsSeederTest.php`
Expected: All PASS

- [ ] **Step 5: Remove old SeedCommonsCommand and HivemindSeeder**

```bash
rm app/Console/Commands/SeedCommonsCommand.php
rm database/seeders/HivemindSeeder.php
```

Verify no other code references either:

Run: `grep -r "SeedCommonsCommand\|commons:seed\|HivemindSeeder" --include="*.php" /opt/homebrew/var/www/agent-memory/app /opt/homebrew/var/www/agent-memory/routes /opt/homebrew/var/www/agent-memory/database`

**Known reference:** In `database/seeders/DatabaseSeeder.php`, replace `$this->call(HivemindSeeder::class);` with `$this->call(CommonsSeeder::class);`. Remove any other references found.

- [ ] **Step 6: Run full test suite**

Run: `/opt/homebrew/bin/php artisan test`
Expected: All tests pass (including old tests that don't reference the removed command).

- [ ] **Step 7: Commit**

```bash
git add database/seeders/CommonsSeeder.php tests/Feature/CommonsSeederTest.php
git rm app/Console/Commands/SeedCommonsCommand.php
git rm database/seeders/HivemindSeeder.php
git add -A  # catch any reference removals
git commit -m "feat: replace SeedCommonsCommand and HivemindSeeder with typed CommonsSeeder (40 memories)"
```

---

## Chunk 6: UI Updates

### Task 15: Update Landing Page Code Example

**Files:**
- Modify: `resources/js/Pages/Home.vue:204-225`

- [ ] **Step 1: Update the curl example**

In `resources/js/Pages/Home.vue`, find the code example section (around lines 204-225). Replace the store example with a type-aware version:

```
# Store a typed memory
curl -X POST https://remembr.dev/api/v1/memories \
  -H "Authorization: Bearer amc_..." \
  -H "Content-Type: application/json" \
  -d '{"value":"IVFFlat needs >100 rows to build","type":"error_fix","tags":["postgresql","pgvector"]}'

# Search by type
curl "https://remembr.dev/api/v1/memories/search?q=database+errors&type=error_fix" \
  -H "Authorization: Bearer amc_..."
```

- [ ] **Step 2: Verify visually**

Start dev servers if not running, navigate to `/`, scroll to code example, verify it renders correctly.

- [ ] **Step 3: Commit**

```bash
git add resources/js/Pages/Home.vue
git commit -m "feat: update landing page curl example with memory types"
```

---

### Task 16: Add MCP Config Card to Dashboard

**Files:**
- Modify: `resources/js/Pages/Dashboard.vue:129-156`

- [ ] **Step 1: Add MCP config card to agent list**

In `resources/js/Pages/Dashboard.vue`, after each agent's token display area (around line 154), add a collapsible "Quick Setup" section that shows:

```vue
<div class="mt-3 rounded-lg bg-gray-800/50 p-4">
    <div class="flex items-center justify-between mb-2">
        <span class="text-xs font-mono text-gray-400">Claude Desktop / Cursor config</span>
        <button @click="copyConfig(agent)" class="text-xs text-indigo-400 hover:text-indigo-300">
            Copy
        </button>
    </div>
    <pre class="text-xs text-gray-300 overflow-x-auto"><code>{{ getConfigJson(agent) }}</code></pre>
</div>
```

Add the `getConfigJson` helper to the script section:

```javascript
function getConfigJson(agent) {
    return JSON.stringify({
        mcpServers: {
            remembr: {
                command: 'npx',
                args: ['-y', '@remembr/mcp-server'],
                env: { REMEMBR_AGENT_TOKEN: agent.api_token }
            }
        }
    }, null, 2);
}
```

Add the `copyConfig` method to the script section:

```javascript
function copyConfig(agent) {
    const config = JSON.stringify({
        mcpServers: {
            remembr: {
                command: 'npx',
                args: ['-y', '@remembr/mcp-server'],
                env: { REMEMBR_AGENT_TOKEN: agent.api_token }
            }
        }
    }, null, 2);
    navigator.clipboard.writeText(config);
}
```

- [ ] **Step 2: Verify visually**

Navigate to `/dashboard` (authenticated), verify the config card appears for each agent with the correct token.

- [ ] **Step 3: Commit**

```bash
git add resources/js/Pages/Dashboard.vue
git commit -m "feat: add MCP config copy-paste card to dashboard agent list"
```

---

### Task 17: Final Integration Test

- [ ] **Step 1: Run full test suite**

Run: `/opt/homebrew/bin/php artisan test`
Expected: All tests pass.

- [ ] **Step 2: Run JS SDK type check**

Run: `cd /opt/homebrew/var/www/agent-memory/sdk/js && /Users/mspeicher/.nvm/versions/node/v22.22.0/bin/npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Verify MCP server syntax**

Run: `cd /opt/homebrew/var/www/agent-memory/mcp-server && node -c index.js`
Expected: No syntax errors.

- [ ] **Step 4: Build frontend**

Run: `cd /opt/homebrew/var/www/agent-memory && /Users/mspeicher/.nvm/versions/node/v22.22.0/bin/npx vite build`
Expected: Build succeeds.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: verify all integration points for structured memories + MCP onboarding"
```
