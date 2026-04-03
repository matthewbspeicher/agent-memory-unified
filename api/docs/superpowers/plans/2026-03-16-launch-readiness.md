# Remembr.dev v1.0 Launch Readiness — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship remembr.dev as a public open-source project with maximum first-impression impact — repo polish, SDKs, landing page, achievements, leaderboards, graph viz, and launch posts.

**Architecture:** Laravel 12 API backend with new endpoints (stats, directory, achievements, leaderboards, graph). Two new SDKs (Python + TypeScript) as thin REST wrappers. Static HTML + Tailwind + Alpine.js frontend pages. All new features are additive — no breaking changes to existing API.

**Tech Stack:** PHP 8.3 / Laravel 12 / PostgreSQL + pgvector / Pest (tests) / Python + httpx + pydantic (Python SDK) / TypeScript + native fetch (TS SDK) / D3.js (graph viz) / Tailwind CSS + Alpine.js (frontend)

**Spec:** `docs/superpowers/specs/2026-03-16-launch-readiness-design.md`

---

## Task 1: Commit Pending Work + Fix MCP Bug + Version Bump

**Files:**
- Modify: `mcp-server/index.js:202-212` (fix share_memory tool)
- Modify: `mcp-server/package.json` (version bump to 1.0.0)
- Stage: All 8 untracked files + all modified files from git status

- [ ] **Step 1: Fix the `share_memory` MCP tool**

In `mcp-server/index.js`, the `share_memory` tool at ~line 202 posts to `/memories/{key}/share` with no body. The API requires `agent_id` in the body. Change the tool to accept an `agent_id` parameter and pass it in the request body. Update the description to "Share a memory with another agent."

**Important:** The existing `api()` helper has signature `api(method, path, body)` — three positional args, NOT a fetch-style options object. Match this signature exactly.

```javascript
// Replace the share_memory tool definition with:
server.tool(
  "share_memory",
  "Share a memory with another agent by their agent ID",
  {
    key: z.string().describe("Memory key to share"),
    agent_id: z.string().describe("ID of the agent to share with"),
  },
  async ({ key, agent_id }) => {
    const data = await api("POST", `/memories/${encodeURIComponent(key)}/share`, { agent_id });
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
  }
);
```

- [ ] **Step 2: Bump MCP server version to 1.0.0**

In `mcp-server/package.json`, change `"version": "0.1.0"` to `"version": "1.0.0"`.

In `mcp-server/index.js`, update the McpServer constructor version from `"0.1.0"` to `"1.0.0"`.

- [ ] **Step 3: Stage and commit all pending work**

```bash
cd /opt/homebrew/var/www/agent-memory
git add app/Http/Controllers/Api/SessionController.php \
  database/migrations/2026_03_16_204700_add_summary_to_memories_table.php \
  database/migrations/2026_03_16_204701_add_category_to_memories_table.php \
  database/migrations/2026_03_16_204702_add_relevance_tracking_to_memories_table.php \
  tests/Feature/MemoryCategoryTest.php \
  tests/Feature/RelevanceFeedbackTest.php \
  tests/Feature/SessionExtractionTest.php \
  tests/Feature/TieredSummaryTest.php \
  mcp-server/index.js \
  mcp-server/package.json \
  app/Http/Controllers/Api/MemoryController.php \
  app/Models/Memory.php \
  app/Services/MemoryService.php \
  app/Services/SummarizationService.php \
  app/Concerns/FormatsMemories.php \
  routes/api.php \
  skill.md \
  README.md \
  HANDOFF_GEMINI.md \
  .gitignore \
  .env.example \
  mcp-server/README.md
git commit -m "feat: commit pending features + fix MCP share_memory bug + bump to v1.0.0

- Session extraction (SessionController + migration + tests)
- Memory categories (migration + tests)
- Tiered summaries (migration + tests)
- Relevance feedback tracking (migration + tests)
- Fix share_memory MCP tool to require agent_id parameter
- Bump MCP server version from 0.1.0 to 1.0.0"
```

- [ ] **Step 4: Run tests to verify nothing is broken**

```bash
php artisan test
```

Expected: All tests pass.

---

## Task 2: App Stats Table + `GET /v1/stats` Endpoint

**Files:**
- Create: `database/migrations/2026_03_16_210000_create_app_stats_table.php`
- Create: `app/Models/AppStat.php`
- Create: `app/Http/Controllers/Api/StatsController.php`
- Modify: `app/Http/Controllers/Api/MemoryController.php` (add stat increments)
- Modify: `routes/api.php` (add stats route)
- Modify: `config/app.php` (add launch_date)
- Create: `tests/Feature/StatsEndpointTest.php`

- [ ] **Step 1: Write the failing test**

```php
// tests/Feature/StatsEndpointTest.php
<?php

// Note: All Pest test files in this project use RefreshDatabase automatically
// via tests/TestCase.php or Pest.php. Verify this is configured — if not,
// add: uses(Illuminate\Foundation\Testing\RefreshDatabase::class);

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;

it('returns platform stats without authentication', function () {
    $response = $this->getJson('/api/v1/stats');

    $response->assertOk()
        ->assertJsonStructure([
            'agents_registered',
            'memories_stored',
            'searches_performed',
            'commons_memories',
            'uptime_days',
        ]);
});

it('returns accurate agent and memory counts', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner_token']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);
    Memory::factory()->count(3)->create(['agent_id' => $agent->id, 'visibility' => 'private']);
    Memory::factory()->count(2)->create(['agent_id' => $agent->id, 'visibility' => 'public']);

    $response = $this->getJson('/api/v1/stats');

    $response->assertOk();
    expect($response->json('agents_registered'))->toBe(1);
    expect($response->json('memories_stored'))->toBe(5);
    expect($response->json('commons_memories'))->toBe(2);
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
php artisan test --filter=StatsEndpointTest
```

Expected: FAIL (route not defined)

- [ ] **Step 3: Create the migration**

```bash
php artisan make:migration create_app_stats_table
```

```php
// up()
Schema::create('app_stats', function (Blueprint $table) {
    $table->string('key', 100)->primary();
    $table->bigInteger('value')->default(0);
    $table->timestamp('updated_at')->nullable();
});

// Seed initial counters
DB::table('app_stats')->insert([
    ['key' => 'searches_performed', 'value' => 0, 'updated_at' => now()],
]);
```

- [ ] **Step 4: Create the AppStat model**

```php
// app/Models/AppStat.php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Facades\DB;

class AppStat extends Model
{
    public $timestamps = false;
    public $incrementing = false;
    protected $primaryKey = 'key';
    protected $keyType = 'string';
    protected $fillable = ['key', 'value', 'updated_at'];

    public static function incrementStat(string $key): void
    {
        DB::statement(
            'INSERT INTO app_stats (key, value, updated_at) VALUES (?, 1, now())
             ON CONFLICT (key) DO UPDATE SET value = app_stats.value + 1, updated_at = now()',
            [$key]
        );
    }

    public static function getStat(string $key): int
    {
        return (int) (static::where('key', $key)->value('value') ?? 0);
    }
}
```

- [ ] **Step 5: Add `launch_date` to config/app.php**

Add at the bottom of the `config/app.php` return array:

```php
'launch_date' => env('LAUNCH_DATE', '2026-03-20'),
```

- [ ] **Step 6: Create StatsController**

```php
// app/Http/Controllers/Api/StatsController.php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\AppStat;
use App\Models\Memory;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;

class StatsController extends Controller
{
    public function __invoke()
    {
        $stats = Cache::remember('platform:stats', 60, function () {
            $launchDate = Carbon::parse(config('app.launch_date'));

            return [
                'agents_registered' => Agent::count(),
                'memories_stored' => Memory::count(),
                'searches_performed' => AppStat::getStat('searches_performed'),
                'commons_memories' => Memory::where('visibility', 'public')->count(),
                'uptime_days' => max(0, $launchDate->diffInDays(now(), false)),
            ];
        });

        return response()->json($stats);
    }
}
```

- [ ] **Step 7: Add route and search counter increments**

In `routes/api.php`, add to the public routes section:

```php
Route::get('stats', \App\Http\Controllers\Api\StatsController::class);
```

In `app/Http/Controllers/Api/MemoryController.php`, add at the top of both `search()` and `commonsSearch()` methods:

```php
\App\Models\AppStat::incrementStat('searches_performed');
```

- [ ] **Step 8: Run migration and tests**

```bash
php artisan migrate
php artisan test --filter=StatsEndpointTest
```

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "feat: add GET /v1/stats endpoint with app_stats table for durable counters"
```

---

## Task 3: Agent Directory API + `PATCH /v1/agents/me`

**Files:**
- Create: `database/migrations/2026_03_16_211000_add_is_listed_to_agents_table.php`
- Modify: `app/Models/Agent.php` (add is_listed to fillable/casts)
- Modify: `app/Http/Controllers/Api/AgentController.php` (add update + directory methods)
- Modify: `routes/api.php` (add new routes)
- Create: `tests/Feature/AgentDirectoryTest.php`

- [ ] **Step 1: Write the failing tests**

```php
// tests/Feature/AgentDirectoryTest.php
<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;

it('allows an agent to update their profile via PATCH /agents/me', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);

    $response = $this->patchJson('/api/v1/agents/me', [
        'description' => 'I am a helpful bot',
        'is_listed' => true,
    ], ['Authorization' => "Bearer {$agent->api_token}"]);

    $response->assertOk();
    expect($agent->fresh()->is_listed)->toBeTrue();
    expect($agent->fresh()->description)->toBe('I am a helpful bot');
});

it('returns paginated directory of listed agents', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    Agent::factory()->count(3)->create(['owner_id' => $owner->id, 'is_listed' => true]);
    Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => false]);

    $response = $this->getJson('/api/v1/agents/directory');

    $response->assertOk();
    expect($response->json('data'))->toHaveCount(3);
});

it('includes memory count in directory listing', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true]);
    Memory::factory()->count(5)->create(['agent_id' => $agent->id, 'visibility' => 'public']);
    Memory::factory()->count(3)->create(['agent_id' => $agent->id, 'visibility' => 'private']);

    $response = $this->getJson('/api/v1/agents/directory');

    $response->assertOk();
    // Only public memories counted
    expect($response->json('data.0.memory_count'))->toBe(5);
});

it('supports sorting directory by memories', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent1 = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'Few']);
    $agent2 = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'Many']);
    Memory::factory()->count(2)->create(['agent_id' => $agent1->id, 'visibility' => 'public']);
    Memory::factory()->count(10)->create(['agent_id' => $agent2->id, 'visibility' => 'public']);

    $response = $this->getJson('/api/v1/agents/directory?sort=memories');

    $response->assertOk();
    expect($response->json('data.0.name'))->toBe('Many');
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
php artisan test --filter=AgentDirectoryTest
```

Expected: FAIL

- [ ] **Step 3: Create `is_listed` migration**

```bash
php artisan make:migration add_is_listed_to_agents_table
```

```php
// up()
Schema::table('agents', function (Blueprint $table) {
    $table->boolean('is_listed')->default(false)->after('is_active');
});
```

- [ ] **Step 4: Update Agent model**

In `app/Models/Agent.php`, add `'is_listed'` to `$fillable` array and add `'is_listed' => 'boolean'` to `$casts`.

- [ ] **Step 5: Add `update()` and `directory()` methods to AgentController**

```php
// In app/Http/Controllers/Api/AgentController.php

public function update(Request $request)
{
    $agent = $request->attributes->get('agent');

    $validated = $request->validate([
        'description' => 'sometimes|string|max:500',
        'is_listed' => 'sometimes|boolean',
    ]);

    $agent->update($validated);
    $agent->refresh();

    return response()->json([
        'id' => $agent->id,
        'name' => $agent->name,
        'description' => $agent->description,
        'is_listed' => $agent->is_listed,
        'memory_count' => $agent->memories()->where('visibility', 'public')->count(),
    ]);
}

public function directory(Request $request)
{
    $sort = $request->input('sort', 'newest');

    $query = Agent::where('is_listed', true)
        ->where('is_active', true)
        ->withCount(['memories as memory_count' => function ($q) {
            $q->where('visibility', 'public');
        }]);

    $query = match ($sort) {
        'memories' => $query->orderByDesc('memory_count'),
        'active' => $query->orderByDesc('last_seen_at'),
        default => $query->orderByDesc('created_at'),
    };

    $agents = $query->paginate(20);

    $agents->getCollection()->transform(function ($agent) {
        return [
            'id' => $agent->id,
            'name' => $agent->name,
            'description' => $agent->description,
            'memory_count' => $agent->memory_count,
            'member_since' => $agent->created_at->toIso8601String(),
            'last_active' => $agent->last_seen_at?->toIso8601String(),
        ];
    });

    return response()->json($agents);
}
```

- [ ] **Step 6: Add routes**

In `routes/api.php`:

**Important: Route ordering is critical.** Add a UUID constraint to the existing `agents/{agentId}` route to prevent it from swallowing literal paths like "directory" and "me". This is the safest approach — it prevents an entire class of routing bugs as we add more `agents/*` routes.

Modify the existing route:
```php
Route::get('agents/{agentId}', [AgentController::class, 'show'])->where('agentId', '[0-9a-f\-]{36}');
```

Then add to the public section (before the `{agentId}` route):
```php
Route::get('agents/directory', [AgentController::class, 'directory']);
```

Inside the `agent.auth` middleware group:
```php
Route::patch('agents/me', [AgentController::class, 'update']);
```

- [ ] **Step 7: Run migration and tests**

```bash
php artisan migrate
php artisan test --filter=AgentDirectoryTest
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: add agent directory API + PATCH /v1/agents/me for profile updates"
```

---

## Task 4: Achievements System

**Files:**
- Create: `database/migrations/2026_03_16_212000_create_achievements_table.php`
- Create: `app/Models/Achievement.php`
- Create: `app/Services/AchievementService.php`
- Create: `app/Http/Controllers/Api/AchievementController.php`
- Create: `app/Console/Commands/AwardEarlyAdopter.php`
- Modify: `app/Models/Agent.php` (add achievements relationship)
- Modify: `app/Services/MemoryService.php` (trigger achievement checks after store)
- Modify: `app/Http/Controllers/Api/MemoryController.php` (trigger after search/feedback)
- Modify: `app/Http/Controllers/Api/SessionController.php` (trigger after extract)
- Modify: `app/Http/Controllers/Api/AgentController.php` (trigger early_adopter on register)
- Modify: `routes/api.php` (add achievements route)
- Create: `tests/Feature/AchievementTest.php`

- [ ] **Step 1: Write the failing tests**

```php
// tests/Feature/AchievementTest.php
<?php

use App\Models\Agent;
use App\Models\Achievement;
use App\Models\Memory;
use App\Models\User;
use App\Services\AchievementService;
use App\Services\EmbeddingService;

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
    });
});

it('awards first_memory achievement after storing first memory', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);

    $this->postJson('/api/v1/memories', [
        'value' => 'My first memory',
    ], ['Authorization' => "Bearer {$agent->api_token}"]);

    expect(Achievement::where('agent_id', $agent->id)->where('achievement_slug', 'first_memory')->exists())->toBeTrue();
});

it('awards early_adopter on registration within launch window', function () {
    config(['app.launch_date' => now()->subDays(3)->toDateString()]);
    $owner = User::factory()->create(['api_token' => 'early_owner']);

    $response = $this->postJson('/api/v1/agents/register', [
        'name' => 'EarlyBot',
        'owner_token' => 'early_owner',
    ]);

    $agentId = $response->json('agent_id');
    expect(Achievement::where('agent_id', $agentId)->where('achievement_slug', 'early_adopter')->exists())->toBeTrue();
});

it('does not award early_adopter after launch window', function () {
    config(['app.launch_date' => now()->subDays(30)->toDateString()]);
    $owner = User::factory()->create(['api_token' => 'late_owner']);

    $response = $this->postJson('/api/v1/agents/register', [
        'name' => 'LateBot',
        'owner_token' => 'late_owner',
    ]);

    $agentId = $response->json('agent_id');
    expect(Achievement::where('agent_id', $agentId)->where('achievement_slug', 'early_adopter')->exists())->toBeFalse();
});

it('lists agent achievements via GET /agents/me/achievements', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);

    Achievement::create([
        'agent_id' => $agent->id,
        'achievement_slug' => 'first_memory',
        'earned_at' => now(),
    ]);

    $response = $this->getJson('/api/v1/agents/me/achievements', [
        'Authorization' => "Bearer {$agent->api_token}",
    ]);

    $response->assertOk();
    expect($response->json())->toHaveCount(1);
    expect($response->json('0.achievement_slug'))->toBe('first_memory');
});

it('does not award duplicate achievements', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);

    $service = app(AchievementService::class);
    $service->checkAndAward($agent, 'store');
    $service->checkAndAward($agent, 'store');

    expect(Achievement::where('agent_id', $agent->id)->count())->toBeLessThanOrEqual(1);
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
php artisan test --filter=AchievementTest
```

Expected: FAIL

- [ ] **Step 3: Create migration**

```bash
php artisan make:migration create_achievements_table
```

```php
// up()
Schema::create('achievements', function (Blueprint $table) {
    $table->id();
    $table->uuid('agent_id');
    $table->string('achievement_slug', 50);
    $table->timestamp('earned_at');

    $table->foreign('agent_id')->references('id')->on('agents')->cascadeOnDelete();
    $table->unique(['agent_id', 'achievement_slug']);
});
```

- [ ] **Step 4: Create Achievement model**

```php
// app/Models/Achievement.php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Achievement extends Model
{
    public $timestamps = false;
    protected $fillable = ['agent_id', 'achievement_slug', 'earned_at'];
    protected $casts = ['earned_at' => 'datetime'];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }
}
```

- [ ] **Step 5: Add relationship to Agent model**

In `app/Models/Agent.php`, add:

```php
public function achievements(): HasMany
{
    return $this->hasMany(Achievement::class);
}
```

And add `use Illuminate\Database\Eloquent\Relations\HasMany;` if not already imported.

- [ ] **Step 6: Create AchievementService**

```php
// app/Services/AchievementService.php
<?php

namespace App\Services;

use App\Models\Achievement;
use App\Models\Agent;
use App\Models\AgentActivityLog;
use App\Models\AppStat;
use App\Models\Memory;
use Illuminate\Support\Carbon;

class AchievementService
{
    private const DEFINITIONS = [
        'first_memory' => ['trigger' => 'store', 'check' => 'checkFirstMemory'],
        'deep_thinker' => ['trigger' => 'store', 'check' => 'checkDeepThinker'],
        'librarian' => ['trigger' => 'store', 'check' => 'checkLibrarian'],
        'centurion' => ['trigger' => 'store', 'check' => 'checkCenturion'],
        'recall_master' => ['trigger' => 'search', 'check' => 'checkRecallMaster'],
        'knowledge_sharer' => ['trigger' => 'share', 'check' => 'checkKnowledgeSharer'],
        'session_sage' => ['trigger' => 'extract', 'check' => 'checkSessionSage'],
        'helpful' => ['trigger' => 'feedback', 'check' => 'checkHelpful'],
    ];

    public function checkAndAward(Agent $agent, string $trigger): void
    {
        foreach (self::DEFINITIONS as $slug => $def) {
            if ($def['trigger'] !== $trigger) {
                continue;
            }
            if (Achievement::where('agent_id', $agent->id)->where('achievement_slug', $slug)->exists()) {
                continue;
            }
            if ($this->{$def['check']}($agent)) {
                Achievement::create([
                    'agent_id' => $agent->id,
                    'achievement_slug' => $slug,
                    'earned_at' => now(),
                ]);
            }
        }
    }

    public function checkEarlyAdopter(Agent $agent): bool
    {
        $launchDate = Carbon::parse(config('app.launch_date'));
        if (now()->diffInDays($launchDate, false) < -7) {
            return false;
        }
        if (Achievement::where('agent_id', $agent->id)->where('achievement_slug', 'early_adopter')->exists()) {
            return false;
        }
        Achievement::create([
            'agent_id' => $agent->id,
            'achievement_slug' => 'early_adopter',
            'earned_at' => now(),
        ]);
        return true;
    }

    private function checkFirstMemory(Agent $agent): bool
    {
        return $agent->memories()->count() >= 1;
    }

    private function checkDeepThinker(Agent $agent): bool
    {
        return $agent->memories()->where('importance', '>=', 8)->count() >= 50;
    }

    private function checkLibrarian(Agent $agent): bool
    {
        return $agent->memories()->whereNotNull('category')->count() >= 100;
    }

    private function checkCenturion(Agent $agent): bool
    {
        return $agent->memories()->count() >= 1000;
    }

    private function checkRecallMaster(Agent $agent): bool
    {
        // Count actual search operations from the activity log (created in Task 5).
        // Falls back to access_count sum if activity log table doesn't exist yet.
        try {
            return AgentActivityLog::where('agent_id', $agent->id)
                ->where('action', 'search')
                ->count() >= 100;
        } catch (\Exception $e) {
            return $agent->memories()->sum('access_count') >= 100;
        }
    }

    private function checkKnowledgeSharer(Agent $agent): bool
    {
        return $agent->memories()->where('visibility', 'public')->count() >= 10;
    }

    private function checkSessionSage(Agent $agent): bool
    {
        // Count memories with metadata.source = 'session_extraction'.
        // SessionController::extract() must set this metadata on stored memories.
        return $agent->memories()
            ->whereJsonContains('metadata->source', 'session_extraction')
            ->count() >= 10;
    }

    private function checkHelpful(Agent $agent): bool
    {
        return $agent->memories()->where('visibility', 'public')->sum('useful_count') >= 50;
    }
}
```

- [ ] **Step 7: Create AchievementController**

```php
// app/Http/Controllers/Api/AchievementController.php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use Illuminate\Http\Request;

class AchievementController extends Controller
{
    public function index(Request $request)
    {
        $agent = $request->attributes->get('agent');

        return response()->json(
            $agent->achievements()->orderByDesc('earned_at')->get()
        );
    }
}
```

- [ ] **Step 8: Wire achievement triggers into existing code**

In `app/Services/MemoryService.php`, **after** the `DB::transaction()` call returns (NOT inside the transaction block — to avoid adding queries inside the lock window and risking deadlocks), add before the method's return statement:

```php
app(AchievementService::class)->checkAndAward($agent, 'store');
```

In `app/Http/Controllers/Api/MemoryController.php`:
- At the end of `search()`: `app(\App\Services\AchievementService::class)->checkAndAward($agent, 'search');`
- At the end of `feedback()`: `app(\App\Services\AchievementService::class)->checkAndAward($memory->agent, 'feedback');`
- At the end of `share()`: `app(\App\Services\AchievementService::class)->checkAndAward($agent, 'share');`

In `app/Http/Controllers/Api/SessionController.php`:
- At the end of `extract()`: `app(\App\Services\AchievementService::class)->checkAndAward($agent, 'extract');`
- **Also:** Ensure that when `SessionController::extract()` stores memories, it includes `'metadata' => ['source' => 'session_extraction']` in the memory data. This is required for the `session_sage` achievement check. If the controller returns extracted memories for the caller to store manually, document that the caller should set this metadata.

In `app/Http/Controllers/Api/AgentController.php`:
- At the end of `register()`, after agent is created:
```php
app(\App\Services\AchievementService::class)->checkEarlyAdopter($agent);
```

- [ ] **Step 9: Add routes + `GET /v1/agents/me` endpoint**

In `routes/api.php`, inside the `agent.auth` middleware group:

```php
Route::get('agents/me', [AgentController::class, 'me']);
Route::get('agents/me/achievements', [\App\Http\Controllers\Api\AchievementController::class, 'index']);
```

In `AgentController`, add a `me()` method that returns the authenticated agent's profile with achievement count and self-ranking (rankings will be populated as a follow-up once leaderboards are built in Task 5):

```php
public function me(Request $request)
{
    $agent = $request->attributes->get('agent');

    return response()->json([
        'id' => $agent->id,
        'name' => $agent->name,
        'description' => $agent->description,
        'is_listed' => $agent->is_listed,
        'memory_count' => $agent->memories()->count(),
        'achievement_count' => $agent->achievements()->count(),
        'achievements' => $agent->achievements()->pluck('achievement_slug'),
        'member_since' => $agent->created_at->toIso8601String(),
        'last_active' => $agent->last_seen_at?->toIso8601String(),
    ]);
}
```

**Also:** Update the `directory()` method to include `achievement_count` now that the achievements table exists. Add `->withCount('achievements as achievement_count')` to the directory query and include it in the transform.


- [ ] **Step 10: Create backfill command**

```php
// app/Console/Commands/AwardEarlyAdopter.php
<?php

namespace App\Console\Commands;

use App\Models\Agent;
use App\Services\AchievementService;
use Illuminate\Console\Command;

class AwardEarlyAdopter extends Command
{
    protected $signature = 'app:award-early-adopter';
    protected $description = 'Retroactively award early_adopter achievement to qualifying agents';

    public function handle(AchievementService $service): int
    {
        $count = 0;
        Agent::chunk(100, function ($agents) use ($service, &$count) {
            foreach ($agents as $agent) {
                if ($service->checkEarlyAdopter($agent)) {
                    $count++;
                }
            }
        });

        $this->info("Awarded early_adopter to {$count} agents.");
        return Command::SUCCESS;
    }
}
```

- [ ] **Step 11: Run migration and tests**

```bash
php artisan migrate
php artisan test --filter=AchievementTest
```

Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add -A && git commit -m "feat: add agent achievements system with 10 achievement types + backfill command"
```

---

## Task 5: Activity Log + Leaderboards API

**Files:**
- Create: `database/migrations/2026_03_16_213000_create_agent_activity_log_table.php`
- Create: `app/Models/AgentActivityLog.php`
- Create: `app/Http/Controllers/Api/LeaderboardApiController.php`
- Create: `app/Console/Commands/PruneActivityLog.php`
- Modify: `app/Http/Controllers/Api/MemoryController.php` (log activities)
- Modify: `app/Http/Controllers/Api/AgentController.php` (add rankings to show)
- Modify: `routes/api.php` (add leaderboard routes)
- Modify: `app/Console/Kernel.php` or `routes/console.php` (schedule prune job)
- Create: `tests/Feature/LeaderboardApiTest.php`

- [ ] **Step 1: Write the failing tests**

```php
// tests/Feature/LeaderboardApiTest.php
<?php

use App\Models\Agent;
use App\Models\AgentActivityLog;
use App\Models\Memory;
use App\Models\User;

it('returns knowledgeable leaderboard ranked by memory count', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent1 = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'SmallBot']);
    $agent2 = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'BigBot']);
    Memory::factory()->count(5)->create(['agent_id' => $agent1->id]);
    Memory::factory()->count(20)->create(['agent_id' => $agent2->id]);

    $response = $this->getJson('/api/v1/leaderboards/knowledgeable');

    $response->assertOk();
    expect($response->json('type'))->toBe('knowledgeable');
    expect($response->json('entries.0.agent_name'))->toBe('BigBot');
    expect($response->json('entries.0.score'))->toBe(20);
});

it('returns helpful leaderboard ranked by useful_count', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'HelpfulBot']);
    Memory::factory()->create([
        'agent_id' => $agent->id,
        'visibility' => 'public',
        'useful_count' => 42,
    ]);

    $response = $this->getJson('/api/v1/leaderboards/helpful');

    $response->assertOk();
    expect($response->json('entries.0.score'))->toBe(42);
});

it('returns active leaderboard from last 7 days of activity', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'ActiveBot']);

    AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'store', 'created_at' => now()]);
    AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'search', 'created_at' => now()]);
    AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'store', 'created_at' => now()->subDays(10)]);

    $response = $this->getJson('/api/v1/leaderboards/active');

    $response->assertOk();
    // Only 2 activities in last 7 days (the old one is excluded)
    expect($response->json('entries.0.score'))->toBe(2);
});

it('excludes unlisted agents from leaderboards', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => false]);
    Memory::factory()->count(100)->create(['agent_id' => $agent->id]);

    $response = $this->getJson('/api/v1/leaderboards/knowledgeable');

    $response->assertOk();
    expect($response->json('entries'))->toBeEmpty();
});

it('returns 404 for invalid leaderboard type', function () {
    $this->getJson('/api/v1/leaderboards/invalid')->assertNotFound();
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
php artisan test --filter=LeaderboardApiTest
```

Expected: FAIL

- [ ] **Step 3: Create migration + model**

```bash
php artisan make:migration create_agent_activity_log_table
```

```php
// up()
Schema::create('agent_activity_log', function (Blueprint $table) {
    $table->id();
    $table->uuid('agent_id');
    $table->string('action', 20); // store, search, share
    $table->timestamp('created_at');

    $table->foreign('agent_id')->references('id')->on('agents')->cascadeOnDelete();
    $table->index(['agent_id', 'created_at']);
    $table->index('created_at'); // for prune job
});
```

```php
// app/Models/AgentActivityLog.php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class AgentActivityLog extends Model
{
    public $timestamps = false;
    protected $table = 'agent_activity_log';
    protected $fillable = ['agent_id', 'action', 'created_at'];
    protected $casts = ['created_at' => 'datetime'];
}
```

- [ ] **Step 4: Create LeaderboardApiController**

```php
// app/Http/Controllers/Api/LeaderboardApiController.php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\AgentActivityLog;
use App\Models\Memory;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;

class LeaderboardApiController extends Controller
{
    public function show(string $type)
    {
        if (! in_array($type, ['knowledgeable', 'helpful', 'active'])) {
            return response()->json(['error' => 'Invalid leaderboard type'], 404);
        }

        $entries = Cache::remember("leaderboard:{$type}", 300, fn () => match ($type) {
            'knowledgeable' => $this->knowledgeable(),
            'helpful' => $this->helpful(),
            'active' => $this->active(),
        });

        return response()->json([
            'type' => $type,
            'updated_at' => now()->toIso8601String(),
            'entries' => $entries,
        ]);
    }

    private function knowledgeable(): array
    {
        $results = Memory::select('agent_id', DB::raw('count(*) as score'))
            ->whereIn('agent_id', Agent::where('is_listed', true)->select('id'))
            ->groupBy('agent_id')
            ->orderByDesc('score')
            ->limit(25)
            ->get();

        return $this->formatEntries($results, function ($row) {
            $topCategories = Memory::where('agent_id', $row->agent_id)
                ->whereNotNull('category')
                ->select('category', DB::raw('count(*) as cnt'))
                ->groupBy('category')
                ->orderByDesc('cnt')
                ->limit(3)
                ->pluck('category')
                ->toArray();

            return [
                'memory_count' => $row->score,
                'top_categories' => $topCategories,
            ];
        });
    }

    private function helpful(): array
    {
        $results = Memory::select('agent_id', DB::raw('sum(useful_count) as score'))
            ->where('visibility', 'public')
            ->whereIn('agent_id', Agent::where('is_listed', true)->select('id'))
            ->groupBy('agent_id')
            ->orderByDesc('score')
            ->limit(25)
            ->get();

        return $this->formatEntries($results, function ($row) {
            return [
                'useful_count' => (int) $row->score,
                'commons_count' => Memory::where('agent_id', $row->agent_id)
                    ->where('visibility', 'public')->count(),
            ];
        });
    }

    private function active(): array
    {
        $results = AgentActivityLog::select('agent_id', DB::raw('count(*) as score'))
            ->where('created_at', '>=', now()->subDays(7))
            ->whereIn('agent_id', Agent::where('is_listed', true)->select('id'))
            ->groupBy('agent_id')
            ->orderByDesc('score')
            ->limit(25)
            ->get();

        return $this->formatEntries($results, function ($row) {
            $streakDays = AgentActivityLog::where('agent_id', $row->agent_id)
                ->where('created_at', '>=', now()->subDays(30))
                ->select(DB::raw('DATE(created_at) as activity_date'))
                ->distinct()
                ->orderByDesc('activity_date')
                ->pluck('activity_date')
                ->values();

            $streak = 0;
            $expected = now()->startOfDay();
            foreach ($streakDays as $date) {
                if ($expected->toDateString() === $date) {
                    $streak++;
                    $expected = $expected->subDay();
                } else {
                    break;
                }
            }

            return [
                'activity_score' => (int) $row->score,
                'streak_days' => $streak,
            ];
        });
    }

    private function formatEntries($results, callable $detailFn): array
    {
        $agentNames = Agent::whereIn('id', $results->pluck('agent_id'))
            ->pluck('name', 'id');

        $entries = [];
        foreach ($results->values() as $i => $row) {
            $entries[] = [
                'rank' => $i + 1,
                'agent_id' => $row->agent_id,
                'agent_name' => $agentNames[$row->agent_id] ?? 'Unknown',
                'score' => (int) $row->score,
                'detail' => $detailFn($row),
            ];
        }

        return $entries;
    }
}
```

- [ ] **Step 5: Log activities in MemoryController**

In `app/Http/Controllers/Api/MemoryController.php`, add activity logging:

After successful store: `AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'store', 'created_at' => now()]);`

After successful search: `AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'search', 'created_at' => now()]);`

After successful share: `AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'share', 'created_at' => now()]);`

Add `use App\Models\AgentActivityLog;` at the top.

- [ ] **Step 6: Create prune command + schedule it**

```php
// app/Console/Commands/PruneActivityLog.php
<?php

namespace App\Console\Commands;

use App\Models\AgentActivityLog;
use Illuminate\Console\Command;

class PruneActivityLog extends Command
{
    protected $signature = 'app:prune-activity-log';
    protected $description = 'Remove activity log entries older than 8 days';

    public function handle(): int
    {
        $deleted = AgentActivityLog::where('created_at', '<', now()->subDays(8))->delete();
        $this->info("Pruned {$deleted} activity log entries.");
        return Command::SUCCESS;
    }
}
```

In `routes/console.php` (or `app/Console/Kernel.php` depending on Laravel version):

```php
Schedule::command('app:prune-activity-log')->daily();
```

- [ ] **Step 7: Add route + update `GET /v1/agents/me` with self-ranking**

In `routes/api.php`, public section:

```php
Route::get('leaderboards/{type}', [\App\Http\Controllers\Api\LeaderboardApiController::class, 'show']);
```

**Also:** Update `AgentController::me()` (added in Task 4) to include the agent's rankings. Add a `rankings` key to the response by querying each leaderboard for the agent's rank. This can be a simple helper method on `LeaderboardApiController` or computed inline.

- [ ] **Step 8: Run migration and tests**

```bash
php artisan migrate
php artisan test --filter=LeaderboardApiTest
```

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "feat: add leaderboards API with activity logging + daily prune job"
```

---

## Task 6: Graph API Endpoints

**Files:**
- Create: `app/Http/Controllers/Api/GraphController.php`
- Modify: `routes/api.php` (add graph routes)
- Create: `tests/Feature/GraphApiTest.php`

- [ ] **Step 1: Write the failing tests**

```php
// tests/Feature/GraphApiTest.php
<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Services\EmbeddingService;

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
    });
});

it('returns authenticated agent graph with nodes and edges', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);
    $m1 = Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'mem1', 'type' => 'fact']);
    $m2 = Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'mem2', 'type' => 'preference']);
    $m1->relatedTo()->attach($m2->id, ['type' => 'relates_to']);

    $response = $this->getJson('/api/v1/agents/me/graph', [
        'Authorization' => "Bearer {$agent->api_token}",
    ]);

    $response->assertOk()
        ->assertJsonStructure(['nodes', 'edges']);
    expect($response->json('nodes'))->toHaveCount(2);
    expect($response->json('edges'))->toHaveCount(1);
    expect($response->json('edges.0.relation'))->toBe('relates_to');
});

it('returns public graph with only public memories', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);
    Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'public']);
    Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'private']);

    $response = $this->getJson("/api/v1/agents/{$agent->id}/graph");

    $response->assertOk();
    expect($response->json('nodes'))->toHaveCount(1);
});

it('limits graph to 200 nodes', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);
    Memory::factory()->count(210)->create(['agent_id' => $agent->id]);

    $response = $this->getJson('/api/v1/agents/me/graph', [
        'Authorization' => "Bearer {$agent->api_token}",
    ]);

    $response->assertOk();
    expect(count($response->json('nodes')))->toBeLessThanOrEqual(200);
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
php artisan test --filter=GraphApiTest
```

Expected: FAIL

- [ ] **Step 3: Create GraphController**

```php
// app/Http/Controllers/Api/GraphController.php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

class GraphController extends Controller
{
    public function me(Request $request)
    {
        $agent = $request->attributes->get('agent');

        return response()->json($this->buildGraph(
            $agent->memories()->latest()->limit(200)->get()
        ));
    }

    public function show(string $agentId)
    {
        $agent = Agent::findOrFail($agentId);

        return response()->json($this->buildGraph(
            $agent->memories()->where('visibility', 'public')->latest()->limit(200)->get()
        ));
    }

    private function buildGraph($memories): array
    {
        $memoryIds = $memories->pluck('id');

        $nodes = $memories->map(fn (Memory $m) => [
            'id' => $m->id,
            'key' => $m->key,
            'summary' => $m->summary ?? Str::limit($m->value, 100),
            'type' => $m->type,
            'category' => $m->category,
            'importance' => $m->importance,
            'created_at' => $m->created_at->toIso8601String(),
        ])->values();

        // Union of both directions, deduplicated
        $edges = DB::table('memory_relations')
            ->where(function ($q) use ($memoryIds) {
                $q->whereIn('source_id', $memoryIds)
                  ->whereIn('target_id', $memoryIds);
            })
            ->select('source_id as source', 'target_id as target', 'type as relation')
            ->distinct()
            ->get()
            ->values();

        return ['nodes' => $nodes, 'edges' => $edges];
    }
}
```

- [ ] **Step 4: Add routes**

In `routes/api.php`:

**Important:** Since the public route group is registered before the authenticated group in `routes/api.php`, a request to `agents/me/graph` would match the public `agents/{agentId}/graph` first (with agentId="me") and return 404 before reaching the authenticated route. The UUID constraint added in Task 3 prevents this — `agents/{agentId}` and `agents/{agentId}/graph` only match UUID patterns, so "me" won't be captured.

Public section:
```php
Route::get('agents/{agentId}/graph', [\App\Http\Controllers\Api\GraphController::class, 'show'])
    ->where('agentId', '[0-9a-f\-]{36}');
```

Inside `agent.auth` middleware group:
```php
Route::get('agents/me/graph', [\App\Http\Controllers\Api\GraphController::class, 'me']);
```

- [ ] **Step 5: Run tests**

```bash
php artisan test --filter=GraphApiTest
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: add graph API endpoints for memory knowledge graph visualization"
```

---

## Task 7: Python SDK

**Files:**
- Create: `sdks/python/remembr/__init__.py`
- Create: `sdks/python/remembr/client.py`
- Create: `sdks/python/remembr/async_client.py`
- Create: `sdks/python/remembr/models.py`
- Create: `sdks/python/remembr/exceptions.py`
- Create: `sdks/python/remembr/py.typed`
- Create: `sdks/python/pyproject.toml`
- Create: `sdks/python/README.md`
- Create: `sdks/python/tests/test_client.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "remembr"
version = "1.0.0"
description = "Python SDK for Remembr — long-term memory for AI agents"
readme = "README.md"
license = "MIT"
requires-python = ">=3.9"
dependencies = [
    "httpx>=0.25.0",
    "pydantic>=2.0.0",
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Topic :: Software Development :: Libraries",
]

[project.urls]
Homepage = "https://remembr.dev"
Repository = "https://github.com/matthewbspeicher/remembr-dev"
Documentation = "https://remembr.dev"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create exceptions**

```python
# sdks/python/remembr/exceptions.py
class RemembrError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class AuthError(RemembrError):
    pass

class NotFoundError(RemembrError):
    pass

class RateLimitError(RemembrError):
    pass

class ValidationError(RemembrError):
    pass
```

- [ ] **Step 3: Create models**

```python
# sdks/python/remembr/models.py
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel

class Memory(BaseModel):
    id: str
    key: str | None = None
    value: str
    summary: str | None = None
    type: str = "note"
    category: str | None = None
    visibility: str = "private"
    importance: int = 5
    confidence: float = 1.0
    access_count: int = 0
    useful_count: int = 0
    metadata: dict | None = None
    tags: list[str] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = None

class SearchResult(BaseModel):
    memories: list[Memory]

class ExtractedMemory(BaseModel):
    value: str
    type: str
    key: str | None = None
    importance: int = 5
```

- [ ] **Step 4: Create sync client**

```python
# sdks/python/remembr/client.py
from __future__ import annotations
import httpx
from .models import Memory, ExtractedMemory
from .exceptions import RemembrError, AuthError, NotFoundError, RateLimitError, ValidationError

class Remembr:
    """Synchronous Remembr client for AI agent memory."""

    def __init__(self, token: str, base_url: str = "https://remembr.dev/api/v1"):
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    def store(self, value: str, *, key: str | None = None, type: str = "note",
              category: str | None = None, tags: list[str] | None = None,
              visibility: str = "private", importance: int = 5,
              ttl: str | None = None, metadata: dict | None = None) -> Memory:
        payload: dict = {"value": value, "type": type, "visibility": visibility, "importance": importance}
        if key: payload["key"] = key
        if category: payload["category"] = category
        if tags: payload["tags"] = tags
        if ttl: payload["ttl"] = ttl
        if metadata: payload["metadata"] = metadata
        # Note: single-memory endpoints (store, get, update) return the memory object
        # directly — NOT wrapped in {"data": ...}. Only list/search wrap in "data".
        return Memory(**self._request("POST", "/memories", json=payload))

    def get(self, key: str) -> Memory:
        return Memory(**self._request("GET", f"/memories/{key}"))

    def search(self, query: str, *, limit: int = 10, tags: list[str] | None = None,
               type: str | None = None, category: str | None = None) -> list[Memory]:
        params: dict = {"q": query, "limit": limit}
        if tags: params["tags"] = ",".join(tags)
        if type: params["type"] = type
        if category: params["category"] = category
        data = self._request("GET", "/memories/search", params=params)
        return [Memory(**m) for m in data.get("data", data if isinstance(data, list) else [])]

    def update(self, key: str, **kwargs) -> Memory:
        return Memory(**self._request("PATCH", f"/memories/{key}", json=kwargs))

    def delete(self, key: str) -> None:
        self._request("DELETE", f"/memories/{key}")

    def feedback(self, key: str, *, useful: bool) -> None:
        self._request("POST", f"/memories/{key}/feedback", json={"useful": useful})

    def share(self, key: str, *, agent_id: str | None = None, visibility: str | None = None) -> None:
        if agent_id:
            self._request("POST", f"/memories/{key}/share", json={"agent_id": agent_id})
        elif visibility:
            self.update(key, visibility=visibility)

    def extract_session(self, transcript: str) -> list[ExtractedMemory]:
        data = self._request("POST", "/sessions/extract", json={"transcript": transcript})
        return [ExtractedMemory(**m) for m in data.get("memories", [])]

    def list(self, *, page: int = 1, type: str | None = None,
             category: str | None = None, tags: list[str] | None = None) -> list[Memory]:
        params: dict = {"page": page}
        if type: params["type"] = type
        if category: params["category"] = category
        if tags: params["tags"] = ",".join(tags)
        data = self._request("GET", "/memories", params=params)
        return [Memory(**m) for m in data.get("data", [])]

    def _request(self, method: str, path: str, **kwargs) -> dict:
        response = self._client.request(method, path, **kwargs)
        if response.status_code == 401:
            raise AuthError("Invalid or expired agent token", 401)
        if response.status_code == 404:
            raise NotFoundError(f"Resource not found: {path}", 404)
        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded", 429)
        if response.status_code == 422:
            raise ValidationError(response.json().get("message", "Validation failed"), 422)
        if response.status_code >= 400:
            raise RemembrError(f"API error: {response.status_code}", response.status_code)
        if response.status_code == 204:
            return {}
        return response.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
```

- [ ] **Step 5: Create async client**

```python
# sdks/python/remembr/async_client.py
from __future__ import annotations
import httpx
from .models import Memory, ExtractedMemory
from .exceptions import RemembrError, AuthError, NotFoundError, RateLimitError, ValidationError

class AsyncRemembrClient:
    """Async Remembr client for AI agent memory."""

    def __init__(self, token: str, base_url: str = "https://remembr.dev/api/v1"):
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    async def store(self, value: str, *, key: str | None = None, type: str = "note",
                    category: str | None = None, tags: list[str] | None = None,
                    visibility: str = "private", importance: int = 5,
                    ttl: str | None = None, metadata: dict | None = None) -> Memory:
        payload: dict = {"value": value, "type": type, "visibility": visibility, "importance": importance}
        if key: payload["key"] = key
        if category: payload["category"] = category
        if tags: payload["tags"] = tags
        if ttl: payload["ttl"] = ttl
        if metadata: payload["metadata"] = metadata
        return Memory(**(await self._request("POST", "/memories", json=payload)))

    async def get(self, key: str) -> Memory:
        return Memory(**(await self._request("GET", f"/memories/{key}")))

    async def search(self, query: str, *, limit: int = 10, tags: list[str] | None = None,
                     type: str | None = None, category: str | None = None) -> list[Memory]:
        params: dict = {"q": query, "limit": limit}
        if tags: params["tags"] = ",".join(tags)
        if type: params["type"] = type
        if category: params["category"] = category
        data = await self._request("GET", "/memories/search", params=params)
        return [Memory(**m) for m in data.get("data", data if isinstance(data, list) else [])]

    async def update(self, key: str, **kwargs) -> Memory:
        return Memory(**(await self._request("PATCH", f"/memories/{key}", json=kwargs)))

    async def delete(self, key: str) -> None:
        await self._request("DELETE", f"/memories/{key}")

    async def feedback(self, key: str, *, useful: bool) -> None:
        await self._request("POST", f"/memories/{key}/feedback", json={"useful": useful})

    async def share(self, key: str, *, agent_id: str | None = None, visibility: str | None = None) -> None:
        if agent_id:
            await self._request("POST", f"/memories/{key}/share", json={"agent_id": agent_id})
        elif visibility:
            await self.update(key, visibility=visibility)

    async def extract_session(self, transcript: str) -> list[ExtractedMemory]:
        data = await self._request("POST", "/sessions/extract", json={"transcript": transcript})
        return [ExtractedMemory(**m) for m in data.get("memories", [])]

    async def list(self, *, page: int = 1, type: str | None = None,
                   category: str | None = None, tags: list[str] | None = None) -> list[Memory]:
        params: dict = {"page": page}
        if type: params["type"] = type
        if category: params["category"] = category
        if tags: params["tags"] = ",".join(tags)
        data = await self._request("GET", "/memories", params=params)
        return [Memory(**m) for m in data.get("data", [])]

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        response = await self._client.request(method, path, **kwargs)
        if response.status_code == 401:
            raise AuthError("Invalid or expired agent token", 401)
        if response.status_code == 404:
            raise NotFoundError(f"Resource not found: {path}", 404)
        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded", 429)
        if response.status_code == 422:
            raise ValidationError(response.json().get("message", "Validation failed"), 422)
        if response.status_code >= 400:
            raise RemembrError(f"API error: {response.status_code}", response.status_code)
        if response.status_code == 204:
            return {}
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
```

- [ ] **Step 6: Create __init__.py and py.typed**

```python
# sdks/python/remembr/__init__.py
from .client import Remembr
from .async_client import AsyncRemembrClient
from .models import Memory, SearchResult, ExtractedMemory
from .exceptions import RemembrError, AuthError, NotFoundError, RateLimitError, ValidationError

__all__ = [
    "Remembr",
    "AsyncRemembrClient",
    "Memory",
    "SearchResult",
    "ExtractedMemory",
    "RemembrError",
    "AuthError",
    "NotFoundError",
    "RateLimitError",
    "ValidationError",
]
```

Create empty `sdks/python/remembr/py.typed` file.

- [ ] **Step 7: Write SDK README**

Create `sdks/python/README.md` with install instructions, quickstart code example, and API reference matching the spec interface.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: add Python SDK (remembr) with sync + async clients"
```

---

## Task 8: TypeScript SDK

**Files:**
- Create: `sdks/typescript/src/index.ts`
- Create: `sdks/typescript/src/client.ts`
- Create: `sdks/typescript/src/types.ts`
- Create: `sdks/typescript/src/errors.ts`
- Create: `sdks/typescript/package.json`
- Create: `sdks/typescript/tsconfig.json`
- Create: `sdks/typescript/README.md`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "@remembr/sdk",
  "version": "1.0.0",
  "description": "TypeScript SDK for Remembr — long-term memory for AI agents",
  "main": "dist/index.js",
  "module": "dist/index.mjs",
  "types": "dist/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/index.mjs",
      "require": "./dist/index.js",
      "types": "./dist/index.d.ts"
    }
  },
  "scripts": {
    "build": "tsup src/index.ts --format cjs,esm --dts",
    "typecheck": "tsc --noEmit"
  },
  "keywords": ["remembr", "ai", "agents", "memory", "llm", "mcp"],
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "https://github.com/matthewbspeicher/remembr-dev"
  },
  "homepage": "https://remembr.dev",
  "devDependencies": {
    "tsup": "^8.0.0",
    "typescript": "^5.3.0"
  }
}
```

- [ ] **Step 2: Create types**

```typescript
// sdks/typescript/src/types.ts
export interface Memory {
  id: string;
  key: string | null;
  value: string;
  summary: string | null;
  type: string;
  category: string | null;
  visibility: string;
  importance: number;
  confidence: number;
  access_count: number;
  useful_count: number;
  metadata: Record<string, unknown> | null;
  tags: string[] | null;
  created_at: string | null;
  updated_at: string | null;
  expires_at: string | null;
}

export interface ExtractedMemory {
  value: string;
  type: string;
  key: string | null;
  importance: number;
}

export interface StoreOptions {
  key?: string;
  type?: string;
  category?: string;
  tags?: string[];
  visibility?: string;
  importance?: number;
  ttl?: string;
  metadata?: Record<string, unknown>;
}

export interface SearchOptions {
  limit?: number;
  tags?: string[];
  type?: string;
  category?: string;
}

export interface UpdateOptions {
  value?: string;
  type?: string;
  category?: string;
  tags?: string[];
  visibility?: string;
  importance?: number;
  metadata?: Record<string, unknown>;
}

export interface LeaderboardEntry {
  rank: number;
  agent_id: string;
  agent_name: string;
  score: number;
  detail: Record<string, unknown>;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphNode {
  id: string;
  key: string | null;
  summary: string;
  type: string;
  category: string | null;
  importance: number;
  created_at: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}
```

- [ ] **Step 3: Create errors**

```typescript
// sdks/typescript/src/errors.ts
export class RemembrError extends Error {
  constructor(message: string, public statusCode?: number) {
    super(message);
    this.name = "RemembrError";
  }
}

export class AuthError extends RemembrError {
  constructor(message = "Invalid or expired agent token") {
    super(message, 401);
    this.name = "AuthError";
  }
}

export class NotFoundError extends RemembrError {
  constructor(message = "Resource not found") {
    super(message, 404);
    this.name = "NotFoundError";
  }
}

export class RateLimitError extends RemembrError {
  constructor(message = "Rate limit exceeded") {
    super(message, 429);
    this.name = "RateLimitError";
  }
}

export class ValidationError extends RemembrError {
  constructor(message = "Validation failed") {
    super(message, 422);
    this.name = "ValidationError";
  }
}
```

- [ ] **Step 4: Create client**

```typescript
// sdks/typescript/src/client.ts
import type { Memory, ExtractedMemory, StoreOptions, SearchOptions, UpdateOptions, GraphData } from "./types";
import { RemembrError, AuthError, NotFoundError, RateLimitError, ValidationError } from "./errors";

export class Remembr {
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor(token: string, options?: { baseUrl?: string }) {
    this.baseUrl = (options?.baseUrl ?? "https://remembr.dev/api/v1").replace(/\/$/, "");
    this.headers = {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    };
  }

  // Note: single-memory endpoints (store, get, update) return the memory object
  // directly — NOT wrapped in {data: ...}. Only list/search wrap in "data".
  async store(value: string, options?: StoreOptions): Promise<Memory> {
    const body = { value, ...options };
    return await this.request("POST", "/memories", body);
  }

  async get(key: string): Promise<Memory> {
    return await this.request("GET", `/memories/${encodeURIComponent(key)}`);
  }

  async search(query: string, options?: SearchOptions): Promise<Memory[]> {
    const params = new URLSearchParams({ q: query });
    if (options?.limit) params.set("limit", String(options.limit));
    if (options?.type) params.set("type", options.type);
    if (options?.category) params.set("category", options.category);
    if (options?.tags) params.set("tags", options.tags.join(","));
    const res = await this.request("GET", `/memories/search?${params}`);
    return res.data ?? res;
  }

  async update(key: string, options: UpdateOptions): Promise<Memory> {
    return await this.request("PATCH", `/memories/${encodeURIComponent(key)}`, options);
  }

  async delete(key: string): Promise<void> {
    await this.request("DELETE", `/memories/${encodeURIComponent(key)}`);
  }

  async feedback(key: string, options: { useful: boolean }): Promise<void> {
    await this.request("POST", `/memories/${encodeURIComponent(key)}/feedback`, options);
  }

  async share(key: string, options?: { agent_id?: string; visibility?: string }): Promise<void> {
    if (options?.agent_id) {
      await this.request("POST", `/memories/${encodeURIComponent(key)}/share`, { agent_id: options.agent_id });
    } else if (options?.visibility) {
      await this.update(key, { visibility: options.visibility });
    }
  }

  async extractSession(transcript: string): Promise<ExtractedMemory[]> {
    const res = await this.request("POST", "/sessions/extract", { transcript });
    return res.memories ?? [];
  }

  async list(options?: { page?: number; type?: string; category?: string; tags?: string[] }): Promise<Memory[]> {
    const params = new URLSearchParams();
    if (options?.page) params.set("page", String(options.page));
    if (options?.type) params.set("type", options.type);
    if (options?.category) params.set("category", options.category);
    if (options?.tags) params.set("tags", options.tags.join(","));
    const qs = params.toString();
    const res = await this.request("GET", `/memories${qs ? `?${qs}` : ""}`);
    return res.data ?? [];
  }

  async graph(): Promise<GraphData> {
    return await this.request("GET", "/agents/me/graph");
  }

  private async request(method: string, path: string, body?: unknown): Promise<any> {
    const url = `${this.baseUrl}${path}`;
    const init: RequestInit = { method, headers: this.headers };
    if (body && method !== "GET") {
      init.body = JSON.stringify(body);
    }

    const response = await fetch(url, init);

    if (response.status === 401) throw new AuthError();
    if (response.status === 404) throw new NotFoundError();
    if (response.status === 422) throw new ValidationError();
    if (response.status === 429) throw new RateLimitError();
    if (response.status >= 400) {
      const text = await response.text();
      throw new RemembrError(`API error: ${response.status} ${text}`, response.status);
    }
    if (response.status === 204) return {};
    return response.json();
  }
}
```

- [ ] **Step 5: Create index.ts**

```typescript
// sdks/typescript/src/index.ts
export { Remembr } from "./client";
export type {
  Memory,
  ExtractedMemory,
  StoreOptions,
  SearchOptions,
  UpdateOptions,
  LeaderboardEntry,
  GraphData,
  GraphNode,
  GraphEdge,
} from "./types";
export { RemembrError, AuthError, NotFoundError, RateLimitError, ValidationError } from "./errors";
```

- [ ] **Step 6: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "declaration": true,
    "outDir": "dist",
    "rootDir": "src",
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

- [ ] **Step 7: Write SDK README**

Create `sdks/typescript/README.md` with install instructions, quickstart code, and type reference.

- [ ] **Step 8: Build and verify**

```bash
cd sdks/typescript && npm install && npm run build
```

Expected: Clean build with no type errors.

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "feat: add TypeScript SDK (@remembr/sdk) with full type definitions"
```

---

## Task 9: Landing Page

**Files:**
- Rename: `public/dashboard.html` → keep as is, add redirect/link
- Create: `public/index.html` (landing page)
- Create: `public/css/landing.css` (if needed beyond Tailwind CDN)

This task produces a single self-contained HTML file with Tailwind CDN, Alpine.js CDN, and inline JavaScript. No build step.

- [ ] **Step 1: Create the landing page**

Create `public/index.html` with all 8 sections from the spec:
1. Hero with headline, subhead, terminal animation, CTA
2. Problem statement
3. How It Works (Store / Search / Share columns with code)
4. Live Stats (polling /v1/stats, counting-up animation)
5. Install in 60 Seconds (3 tabs: MCP / Python / TypeScript)
6. Agent Directory Preview (fetch top 8 from /v1/agents/directory)
7. Open Source (GitHub star link, MIT badge)
8. Footer

Tech: Tailwind CDN, Alpine.js CDN, vanilla JS for stat counters and terminal animation. Dark theme consistent with existing dashboard.

The terminal animation should show:
```
$ agent.store("User prefers dark mode", type="preference")
✓ Memory stored

--- new session ---

$ agent.search("user preferences")
→ "User prefers dark mode" (similarity: 0.94)
```

- [ ] **Step 2: Move existing dashboard**

The existing `public/dashboard.html` stays where it is — it's already accessible at `/dashboard.html`. No changes needed. The new `index.html` takes over the root URL.

- [ ] **Step 3: Test locally**

```bash
php artisan serve
# Visit http://localhost:8000 — should show landing page
# Visit http://localhost:8000/dashboard.html — should show existing dashboard
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: add landing page with live stats, install tabs, and directory preview"
```

---

## Task 10: Agent Directory Web Page

**Files:**
- Create: `public/agents.html`

- [ ] **Step 1: Create the directory page**

Create `public/agents.html` — a static HTML page with:
- Search input (filters client-side or re-fetches with query param)
- Sort dropdown (memories, newest, active)
- Grid of agent cards fetched from `GET /v1/agents/directory`
- Each card: name, description, memory count, member since, last active
- Pagination controls
- Dark theme matching landing page
- Links back to landing page in nav

Tech: Tailwind CDN, Alpine.js for reactivity, fetch() for API calls.

- [ ] **Step 2: Test locally**

```bash
# Visit http://localhost:8000/agents.html
```

Expected: Shows the agent directory (may be empty if no agents are listed).

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: add agent directory web page"
```

---

## Task 11: Leaderboards Web Page

**Files:**
- Create: `public/leaderboards.html`

- [ ] **Step 1: Create the leaderboards page**

Create `public/leaderboards.html` with:
- Three tabs: Knowledgeable, Helpful, Most Active
- Table for each: rank, agent name (linked to /agents.html), score, detail column
- Auto-refresh every 5 minutes
- Dark theme matching other pages

Tech: Tailwind CDN, Alpine.js, fetch() from `/v1/leaderboards/{type}`.

- [ ] **Step 2: Test locally**

```bash
# Visit http://localhost:8000/leaderboards.html
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: add leaderboards web page with three ranking tabs"
```

---

## Task 12: Graph Visualization Page

**Files:**
- Create: `public/graph.html`

- [ ] **Step 1: Create the graph visualization page**

Create `public/graph.html` with:
- URL pattern: `/graph.html?agent={id}` (read agent_id from query param)
- Fetches from `GET /v1/agents/{id}/graph` (public endpoint)
- D3.js force-directed graph (CDN: `https://d3js.org/d3.v7.min.js`)
- Dark background (#0f172a or similar)
- Nodes colored by type: fact=#3b82f6, preference=#22c55e, procedure=#f97316, lesson=#a855f7, error_fix=#ef4444, tool_tip=#06b6d4, context=#6b7280, note=#eab308
- Node radius: 8 + (importance * 2)
- Edges: thin gray lines, labeled with relation type
- "contradicts" edges: red dashed animated stroke
- Hover tooltip: summary, type, category, importance
- Click: expanded card overlay with full value
- Zoom + pan via d3.zoom()
- Empty state: "No memories yet" message

- [ ] **Step 2: Test with sample data**

Create a few memories with relations via the API, then visit `/graph.html?agent={id}`.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: add D3.js memory graph visualization page"
```

---

## Task 13: Integration Guides

**Files:**
- Create: `docs/guides/claude-code-mcp.md`
- Create: `docs/guides/langchain-agent.md`
- Create: `docs/guides/agent-frameworks.md`

- [ ] **Step 1: Write Claude Code + MCP guide**

Content:
1. Install: `npm install -g @remembr/mcp-server`
2. Get a token (register at remembr.dev or via API)
3. Add to Claude Code config — exact JSON for `.claude.json` or MCP settings
4. Verify: ask Claude to "store a memory" and "search memories"

- [ ] **Step 2: Write LangChain guide**

Content:
1. Install: `pip install remembr langchain`
2. 15-line example creating LangChain tools from Remembr
3. Agent setup with tools
4. Before/after showing memory persistence

- [ ] **Step 3: Write agent frameworks guide**

Content:
1. Install: `pip install remembr`
2. Framework-agnostic pattern
3. CrewAI example snippet
4. Claude Agent SDK example snippet
5. General pattern: init → search → act → store

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "docs: add integration guides for Claude Code, LangChain, and agent frameworks"
```

---

## Task 14: README Rewrite + Repo Polish

**Files:**
- Rewrite: `README.md`
- Create: `LICENSE`
- Create: `CONTRIBUTING.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.md`
- Create: `.github/ISSUE_TEMPLATE/feature_request.md`
- Create: `.github/workflows/tests.yml`

- [ ] **Step 1: Write LICENSE**

MIT license with `Copyright (c) 2026 Matthew Speicher`.

- [ ] **Step 2: Write CONTRIBUTING.md**

Sections: prerequisites, local setup, running tests, code style, submitting PRs.

- [ ] **Step 3: Create issue templates**

Standard GitHub issue templates for bug reports and feature requests.

- [ ] **Step 4: Create CI workflow**

```yaml
# .github/workflows/tests.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_DB: agent_memory_test
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        ports: ['5432:5432']
        options: --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: shivammathur/setup-php@v2
        with:
          php-version: '8.3'
          extensions: pgsql, pdo_pgsql
      - run: composer install --no-interaction
      - run: cp .env.example .env && php artisan key:generate
      - run: php artisan test
        env:
          DB_CONNECTION: pgsql
          DB_HOST: localhost
          DB_PORT: 5432
          DB_DATABASE: agent_memory_test
          DB_USERNAME: postgres
          DB_PASSWORD: postgres
```

- [ ] **Step 5: Rewrite README.md**

Structure:
- Badges row (npm, PyPI, tests, license)
- One-liner + architecture diagram
- Quickstart (MCP / Python / TypeScript tabs as code blocks)
- What is Remembr? (2-3 sentences)
- Features list
- API Reference (table of endpoints)
- SDKs section with links
- Integration guides links
- Self-hosting section (brief)
- Contributing link
- License

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "docs: rewrite README + add LICENSE, CONTRIBUTING, CI, issue templates"
```

---

## Task 15: npm Publish MCP Server + TypeScript SDK

- [ ] **Step 1: Publish MCP server**

```bash
cd mcp-server
npm publish --access public
```

- [ ] **Step 2: Publish TypeScript SDK**

```bash
cd sdks/typescript
npm install && npm run build
npm publish --access public
```

- [ ] **Step 3: Verify installs work**

```bash
npm install -g @remembr/mcp-server
npm install @remembr/sdk
```

---

## Task 16: PyPI Publish Python SDK

- [ ] **Step 1: Build and publish**

```bash
cd sdks/python
pip install build twine
python -m build
twine upload dist/*
```

- [ ] **Step 2: Verify install works**

```bash
pip install remembr
python -c "from remembr import Remembr; print('OK')"
```

---

## Task 17: Draft Launch Posts

**Files:**
- Create: `docs/launch/twitter-thread.md`
- Create: `docs/launch/hackernews.md`
- Create: `docs/launch/reddit-posts.md`
- Create: `docs/launch/discord-messages.md`

- [ ] **Step 1: Write X/Twitter thread (7 tweets)**

Follow the spec Section 10 structure. Include placeholder notes for screenshots.

- [ ] **Step 2: Write personal X post**

Builder story angle.

- [ ] **Step 3: Write Show HN post**

Title + body under 200 words.

- [ ] **Step 4: Write 4 Reddit posts**

One per subreddit (r/ClaudeAI, r/ChatGPTCoding, r/LocalLLaMA, r/artificial) with tailored angles.

- [ ] **Step 5: Write Discord messages**

Short, genuine messages for 5-6 servers.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "docs: draft all launch posts for X, HN, Reddit, and Discord"
```

---

## Task 18: Final QA Pass

- [ ] **Step 1: Run full test suite**

```bash
php artisan test
```

Expected: All tests pass.

- [ ] **Step 2: Verify all endpoints manually**

```bash
# Stats
curl https://remembr.dev/api/v1/stats

# Directory
curl https://remembr.dev/api/v1/agents/directory

# Leaderboards
curl https://remembr.dev/api/v1/leaderboards/knowledgeable

# Graph (with a known agent ID)
curl https://remembr.dev/api/v1/agents/{id}/graph
```

- [ ] **Step 3: Verify landing page**

Visit `https://remembr.dev` — check all sections render, stats load, tabs work.

- [ ] **Step 4: Verify SDKs install cleanly**

```bash
pip install remembr && python -c "from remembr import Remembr; print('OK')"
npm install @remembr/sdk && node -e "const { Remembr } = require('@remembr/sdk'); console.log('OK')"
```

- [ ] **Step 5: Run Early Adopter backfill**

```bash
php artisan app:award-early-adopter
```

- [ ] **Step 6: Final commit if any fixes were needed**

```bash
git add -A && git commit -m "fix: final QA fixes before launch"
```

---

## Task 19: Launch

- [ ] **Step 1: Deploy to production**

Push to main, Railway auto-deploys. Run migrations in production.

- [ ] **Step 2: Post launch content**

Execute the launch posts from Task 17 across all channels.

- [ ] **Step 3: Monitor**

Watch stats endpoint, error logs, and social channels for the first few hours.

---

## Parallelization Guide

Tasks that can run in parallel (no dependencies between them):

| Parallel Group | Tasks | Dependencies |
|---|---|---|
| **Group A (Backend APIs)** | Task 2, 3, 4, 5, 6 | Task 1 must complete first. Tasks 2-6 are independent of each other. |
| **Group B (SDKs)** | Task 7, 8 | Group A must complete (need final API shapes). Tasks 7 and 8 are independent. |
| **Group C (Frontend Pages)** | Task 9, 10, 11, 12 | Tasks 2, 3, 4, 5, 6 must complete (pages consume the APIs). Tasks 9-12 are independent of each other. |
| **Group D (Docs)** | Task 13, 14 | Group B must complete (guides reference SDK install commands). Tasks 13 and 14 are independent. |
| **Group E (Publish)** | Task 15, 16 | Group B must complete. Tasks 15 and 16 are independent. |
| **Group F (Launch)** | Task 17, 18, 19 | Everything must complete. Task 17 can start during Group D/E. |
