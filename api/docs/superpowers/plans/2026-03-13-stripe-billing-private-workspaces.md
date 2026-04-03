# Stripe Billing & Private Workspaces Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Free/Pro ($49/mo) subscription tiers with Stripe Checkout, gating private workspaces and higher quotas behind Pro, with soft-lock downgrade behavior.

**Architecture:** Laravel Cashier manages all Stripe interactions. The User model gains a `Billable` trait and plan-checking helpers. Three enforcement points (agent cap, workspace gate, soft-lock middleware) check subscription status server-side. A webhook listener syncs agent quotas when subscription status changes.

**Tech Stack:** Laravel Cashier (Stripe), Stripe Checkout, Stripe Customer Portal, Inertia.js + Vue 3

**Spec:** `docs/superpowers/specs/2026-03-13-stripe-billing-private-workspaces-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `config/stripe.php` | Pro price ID config |
| `app/Http/Controllers/BillingController.php` | Checkout, success, portal, pricing actions |
| `app/Listeners/SyncAgentQuotas.php` | Sync agent `max_memories` on subscription changes |
| `resources/js/Pages/Pricing.vue` | Public pricing page (two-card layout) |
| `tests/Feature/BillingTest.php` | All billing/enforcement tests |

### Modified Files
| File | Change |
|------|--------|
| `composer.json` | Add `laravel/cashier-stripe` |
| `.env.example` | Add Stripe env vars |
| `app/Models/User.php` | Add `Billable` trait, plan helpers, `ownedWorkspaces()`, `$hidden` updates |
| `app/Http/Controllers/Api/AgentController.php:25-31` | Insert agent cap before create |
| `app/Http/Controllers/Auth/DashboardController.php:22-35` | Insert agent cap + pass billing props |
| `app/Http/Controllers/Api/WorkspaceController.php:20-41` | Insert workspace gate before create |
| `app/Http/Middleware/AuthenticateAgent.php:12-39` | Add soft-lock check after auth |
| `app/Providers/AppServiceProvider.php:24-44` | Register webhook listener |
| `routes/web.php` | Add billing + pricing routes |
| `bootstrap/app.php:14-21` | Add CSRF exclusion for Stripe webhook |
| `resources/js/Pages/Dashboard.vue` | Add billing section |
| `resources/js/Layouts/AppLayout.vue:16-35` | Add Pricing nav link |

---

## Chunk 1: Foundation

### Task 1: Install Cashier & Create Config

**Files:**
- Modify: `composer.json`
- Create: `config/stripe.php`
- Modify: `.env.example`
- Modify: `bootstrap/app.php:14-21`

- [ ] **Step 1: Verify Cashier is already installed**

`laravel/cashier` is already in `composer.json` and Cashier migrations already exist in `database/migrations/`. No install or publish step needed. Verify:

```bash
php artisan migrate:status | grep -i "customer\|subscription"
```

Expected: Cashier migration files listed (create_customer_columns, create_subscriptions_table, create_subscription_items_table, etc.). If any show "Pending", run `php artisan migrate`.

- [ ] **Step 3: Create config/stripe.php**

```php
<?php

return [
    'pro_price_id' => env('STRIPE_PRO_PRICE_ID'),
];
```

- [ ] **Step 4: Add Stripe env vars to .env.example**

Append at the end of `.env.example`, after the `VITE_APP_NAME` line:

```env
STRIPE_KEY=
STRIPE_SECRET=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRO_PRICE_ID=
```

- [ ] **Step 3: Exclude Stripe webhook from CSRF**

In `bootstrap/app.php`, modify the `withMiddleware` closure (lines 14-22) to add CSRF exclusion:

```php
->withMiddleware(function (Middleware $middleware): void {
    $middleware->web(append: [
        \App\Http\Middleware\HandleInertiaRequests::class,
    ]);
    $middleware->alias([
        'agent.auth' => \App\Http\Middleware\AuthenticateAgent::class,
        'rate.headers' => \App\Http\Middleware\RateLimitHeaders::class,
    ]);
    $middleware->validateCsrfTokens(except: ['stripe/*']);
})
```

- [ ] **Step 4: Run existing tests to verify nothing is broken**

```bash
php artisan test
```

Expected: All existing tests pass.

- [ ] **Step 5: Commit**

```bash
git add config/stripe.php .env.example bootstrap/app.php
git commit -m "feat(billing): add Stripe config and CSRF exclusion"
```

---

### Task 2: User Model — Billable Trait & Plan Helpers

**Files:**
- Modify: `app/Models/User.php`
- Test: `tests/Feature/BillingTest.php`

- [ ] **Step 1: Write failing tests for plan helpers**

Create `tests/Feature/BillingTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\User;
use App\Models\Workspace;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

uses(RefreshDatabase::class);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeOwner(array $overrides = []): User
{
    return User::factory()->create(array_merge([
        'api_token' => 'owner_test_token',
    ], $overrides));
}

function makeProUser(array $overrides = []): User
{
    $user = makeOwner(array_merge([
        'stripe_id' => 'cus_test_' . Str::random(10),
    ], $overrides));

    $subscription = $user->subscriptions()->create([
        'type' => 'default',
        'stripe_id' => 'sub_test_' . Str::random(10),
        'stripe_status' => 'active',
        'stripe_price' => config('stripe.pro_price_id') ?: 'price_test',
        'quantity' => 1,
    ]);

    $subscription->items()->create([
        'stripe_id' => 'si_test_' . Str::random(10),
        'stripe_product' => 'prod_test',
        'stripe_price' => config('stripe.pro_price_id') ?: 'price_test',
        'quantity' => 1,
    ]);

    return $user->fresh();
}

function makeAgent(User $owner, array $overrides = []): Agent
{
    return Agent::factory()->create(array_merge([
        'owner_id' => $owner->id,
        'api_token' => 'amc_' . Str::random(40),
    ], $overrides));
}

function withAgent(Agent $agent): array
{
    return ['Authorization' => "Bearer {$agent->api_token}"];
}

// ---------------------------------------------------------------------------
// Plan Helper Tests
// ---------------------------------------------------------------------------

describe('plan helpers', function () {
    it('returns false for isPro when user has no subscription', function () {
        $user = makeOwner();
        expect($user->isPro())->toBeFalse();
    });

    it('returns true for isPro when user has active subscription', function () {
        $user = makeProUser();
        expect($user->isPro())->toBeTrue();
    });

    it('returns 3 max agents for free user', function () {
        $user = makeOwner();
        expect($user->maxAgents())->toBe(3);
    });

    it('returns PHP_INT_MAX max agents for pro user', function () {
        $user = makeProUser();
        expect($user->maxAgents())->toBe(PHP_INT_MAX);
    });

    it('returns 1000 max memories per agent for free user', function () {
        $user = makeOwner();
        expect($user->maxMemoriesPerAgent())->toBe(1000);
    });

    it('returns 10000 max memories per agent for pro user', function () {
        $user = makeProUser();
        expect($user->maxMemoriesPerAgent())->toBe(10000);
    });

    it('returns false for canCreateWorkspace for free user', function () {
        $user = makeOwner();
        expect($user->canCreateWorkspace())->toBeFalse();
    });

    it('returns true for canCreateWorkspace for pro user', function () {
        $user = makeProUser();
        expect($user->canCreateWorkspace())->toBeTrue();
    });

    it('returns true for isDowngraded when not pro but has more than 3 agents', function () {
        $user = makeOwner();
        for ($i = 0; $i < 4; $i++) {
            makeAgent($user);
        }
        expect($user->isDowngraded())->toBeTrue();
    });

    it('returns true for isDowngraded when not pro but owns workspaces', function () {
        $user = makeOwner();
        Workspace::factory()->create(['owner_id' => $user->id]);
        expect($user->isDowngraded())->toBeTrue();
    });

    it('returns false for isDowngraded for pro user with many agents', function () {
        $user = makeProUser();
        for ($i = 0; $i < 5; $i++) {
            makeAgent($user);
        }
        expect($user->isDowngraded())->toBeFalse();
    });

    it('returns false for isDowngraded for free user within limits and no workspaces', function () {
        $user = makeOwner();
        makeAgent($user);
        expect($user->isDowngraded())->toBeFalse();
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
php artisan test tests/Feature/BillingTest.php
```

Expected: FAIL — `isPro()` method not found.

- [ ] **Step 3: Implement User model changes**

Modify `app/Models/User.php`. Full replacement:

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Foundation\Auth\User as Authenticatable;
use Illuminate\Notifications\Notifiable;
use Illuminate\Support\Str;
use Laravel\Cashier\Billable;

class User extends Authenticatable
{
    /** @use HasFactory<\Database\Factories\UserFactory> */
    use HasFactory, Notifiable, Billable;

    protected $fillable = [
        'name',
        'email',
        'password',
        'api_token',
        'magic_link_token',
        'magic_link_expires_at',
    ];

    protected $hidden = [
        'password',
        'remember_token',
        'api_token',
        'magic_link_token',
        'stripe_id',
        'pm_type',
        'pm_last_four',
        'trial_ends_at',
    ];

    protected function casts(): array
    {
        return [
            'email_verified_at' => 'datetime',
            'password' => 'hashed',
            'magic_link_expires_at' => 'datetime',
        ];
    }

    // -------------------------------------------------------------------------
    // Relationships
    // -------------------------------------------------------------------------

    public function agents(): HasMany
    {
        return $this->hasMany(Agent::class, 'owner_id');
    }

    public function sharedWorkspaces(): \Illuminate\Database\Eloquent\Relations\BelongsToMany
    {
        return $this->belongsToMany(Workspace::class, 'workspace_user')
            ->withTimestamps();
    }

    public function ownedGyms(): HasMany
    {
        return $this->hasMany(ArenaGym::class, 'owner_id');
    }

    public function ownedWorkspaces(): HasMany
    {
        return $this->hasMany(Workspace::class, 'owner_id');
    }

    // -------------------------------------------------------------------------
    // Plan helpers
    // -------------------------------------------------------------------------

    public function isPro(): bool
    {
        return $this->subscribed('default');
    }

    public function maxAgents(): int
    {
        return $this->isPro() ? PHP_INT_MAX : 3;
    }

    public function maxMemoriesPerAgent(): int
    {
        return $this->isPro() ? 10_000 : 1_000;
    }

    public function canCreateWorkspace(): bool
    {
        return $this->isPro();
    }

    /**
     * A user is "downgraded" if they are NOT Pro and either:
     * - They have more agents than the free limit (>3), OR
     * - They own any workspaces (workspaces are Pro-only)
     */
    public function isDowngraded(): bool
    {
        if ($this->isPro()) {
            return false;
        }

        return $this->agents()->count() > $this->maxAgents()
            || $this->ownedWorkspaces()->exists();
    }

    public function isOnGracePeriod(): bool
    {
        $sub = $this->subscription('default');

        return $sub && $sub->onGracePeriod();
    }

    public function hasPaymentFailure(): bool
    {
        $sub = $this->subscription('default');

        return $sub && $sub->hasIncompletePayment();
    }

    // -------------------------------------------------------------------------
    // Auth helpers
    // -------------------------------------------------------------------------

    public function generateMagicLink(): string
    {
        $token = Str::random(64);

        $this->update([
            'magic_link_token' => $token,
            'magic_link_expires_at' => now()->addMinutes(30),
        ]);

        return $token;
    }

    public function hasValidMagicLink(string $token): bool
    {
        return $this->magic_link_token === $token
            && $this->magic_link_expires_at
            && $this->magic_link_expires_at->isFuture();
    }

    public function clearMagicLink(): void
    {
        $this->update([
            'magic_link_token' => null,
            'magic_link_expires_at' => null,
        ]);
    }

    public static function generateToken(): string
    {
        return 'own_'.Str::random(40);
    }

    public function ensureApiToken(): string
    {
        if (! $this->api_token) {
            $this->update(['api_token' => self::generateToken()]);
        }

        return $this->api_token;
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
php artisan test tests/Feature/BillingTest.php
```

Expected: All plan helper tests PASS.

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
php artisan test
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/Models/User.php tests/Feature/BillingTest.php
git commit -m "feat(billing): add Billable trait and plan helpers to User model"
```

---

## Chunk 2: Enforcement

### Task 3: Agent Creation Cap

**Files:**
- Modify: `app/Http/Controllers/Api/AgentController.php:25-31`
- Modify: `app/Http/Controllers/Auth/DashboardController.php:22-35`
- Test: `tests/Feature/BillingTest.php` (append)

- [ ] **Step 1: Write failing tests for agent cap**

Append to `tests/Feature/BillingTest.php`:

```php
// ---------------------------------------------------------------------------
// Agent Cap Enforcement
// ---------------------------------------------------------------------------

describe('agent creation cap', function () {
    it('allows free user to register 3 agents via API', function () {
        $owner = makeOwner();
        for ($i = 0; $i < 3; $i++) {
            $response = $this->postJson('/api/v1/agents/register', [
                'name' => "Agent $i",
                'owner_token' => $owner->api_token,
            ]);
            $response->assertStatus(201);
        }
    });

    it('blocks free user from registering 4th agent via API', function () {
        $owner = makeOwner();
        for ($i = 0; $i < 3; $i++) {
            makeAgent($owner);
        }

        $response = $this->postJson('/api/v1/agents/register', [
            'name' => 'Agent 4',
            'owner_token' => $owner->api_token,
        ]);
        $response->assertStatus(403);
        $response->assertJsonFragment(['error' => 'Agent limit reached. Upgrade to Pro for unlimited agents.']);
    });

    it('allows pro user to register unlimited agents via API', function () {
        $owner = makeProUser();
        for ($i = 0; $i < 5; $i++) {
            $response = $this->postJson('/api/v1/agents/register', [
                'name' => "Agent $i",
                'owner_token' => $owner->api_token,
            ]);
            $response->assertStatus(201);
        }
    });

    it('blocks free user from registering 4th agent via dashboard', function () {
        $owner = makeOwner();
        for ($i = 0; $i < 3; $i++) {
            makeAgent($owner);
        }

        $response = $this->actingAs($owner)->post('/dashboard/agents', [
            'name' => 'Agent 4',
        ]);
        $response->assertSessionHasErrors('name');
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
php artisan test tests/Feature/BillingTest.php --filter="agent creation cap"
```

Expected: FAIL — 4th agent still succeeds (no cap yet).

- [ ] **Step 3: Add agent cap to AgentController::register()**

In `app/Http/Controllers/Api/AgentController.php`, insert after line 25 (`$owner = User::where...`) and before line 31 (`$token = Agent::generateToken()`):

```php
        if ($owner->agents()->count() >= $owner->maxAgents()) {
            return response()->json([
                'error' => 'Agent limit reached. Upgrade to Pro for unlimited agents.',
            ], 403);
        }
```

- [ ] **Step 4: Add agent cap to DashboardController::registerAgent()**

In `app/Http/Controllers/Auth/DashboardController.php`, insert after line 27 (closing `]);` of validate) and before line 29 (`$token = Agent::generateToken()`):

```php
        $user = $request->user();

        if ($user->agents()->count() >= $user->maxAgents()) {
            return back()->withErrors(['name' => 'Agent limit reached. Upgrade to Pro for unlimited agents.']);
        }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
php artisan test tests/Feature/BillingTest.php --filter="agent creation cap"
```

Expected: All PASS.

- [ ] **Step 6: Run full test suite**

```bash
php artisan test
```

Expected: All pass. Existing agent registration tests still work (they create owners who have <3 agents).

- [ ] **Step 7: Commit**

```bash
git add app/Http/Controllers/Api/AgentController.php app/Http/Controllers/Auth/DashboardController.php tests/Feature/BillingTest.php
git commit -m "feat(billing): enforce agent creation cap (3 for free, unlimited for pro)"
```

---

### Task 4: Workspace Creation Gate

**Files:**
- Modify: `app/Http/Controllers/Api/WorkspaceController.php:20-41`
- Test: `tests/Feature/BillingTest.php` (append)

- [ ] **Step 1: Write failing tests for workspace gate**

Append to `tests/Feature/BillingTest.php`:

```php
// ---------------------------------------------------------------------------
// Workspace Gate
// ---------------------------------------------------------------------------

describe('workspace creation gate', function () {
    it('blocks free user from creating workspaces', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner);

        $response = $this->postJson('/api/v1/workspaces', [
            'name' => 'Private Workspace',
        ], withAgent($agent));

        $response->assertStatus(403);
        $response->assertJsonFragment(['error' => 'Private workspaces require a Pro subscription.']);
    });

    it('allows pro user to create workspaces', function () {
        $owner = makeProUser();
        $agent = makeAgent($owner);

        $response = $this->postJson('/api/v1/workspaces', [
            'name' => 'Private Workspace',
        ], withAgent($agent));

        $response->assertStatus(201);
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
php artisan test tests/Feature/BillingTest.php --filter="workspace creation gate"
```

Expected: FAIL — free user can currently create workspaces.

- [ ] **Step 3: Replace old B2B workspace gating with new plan-based gate**

In `app/Http/Controllers/Api/WorkspaceController.php`, the current `store()` method has old B2B pricing logic (lines 30-48) that checks `$owner->subscribed('pro')` and enforces a limit of 5 workspaces. Replace the entire block from `$owner = $agent->owner;` through the `if ($currentCount >= $workspaceLimit)` block (lines 30-48) with:

```php
        $owner = $agent->owner;

        if (! $owner->canCreateWorkspace()) {
            return response()->json([
                'error' => 'Private workspaces require a Pro subscription.',
            ], 403);
        }
```

This removes the old 5-workspace limit and replaces it with the new binary Pro/Free gate via `canCreateWorkspace()`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
php artisan test tests/Feature/BillingTest.php --filter="workspace creation gate"
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add app/Http/Controllers/Api/WorkspaceController.php tests/Feature/BillingTest.php
git commit -m "feat(billing): gate workspace creation behind Pro subscription"
```

---

### Task 5: Soft Lock on Downgrade

**Files:**
- Modify: `app/Http/Middleware/AuthenticateAgent.php`
- Test: `tests/Feature/BillingTest.php` (append)

- [ ] **Step 1: Write failing tests for soft lock**

Append to `tests/Feature/BillingTest.php`. These tests need the embedding service mocked:

```php
// ---------------------------------------------------------------------------
// Soft Lock on Downgrade
// ---------------------------------------------------------------------------

describe('soft lock on downgrade', function () {

    beforeEach(function () {
        // Mock embeddings for memory store tests
        $mock = Mockery::mock(\App\Services\EmbeddingService::class);
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        app()->instance(\App\Services\EmbeddingService::class, $mock);
    });

    it('blocks write on 4th agent when downgraded', function () {
        $owner = makeOwner();
        $agents = [];
        for ($i = 0; $i < 4; $i++) {
            $agents[] = makeAgent($owner);
        }

        // 4th agent (by created_at) should be read-only
        $response = $this->postJson('/api/v1/memories', [
            'value' => 'test memory',
        ], withAgent($agents[3]));

        $response->assertStatus(403);
        $response->assertJsonFragment(['error' => 'This agent is in read-only mode. Upgrade to Pro to restore write access.']);
    });

    it('allows read on 4th agent when downgraded', function () {
        $owner = makeOwner();
        $agents = [];
        for ($i = 0; $i < 4; $i++) {
            $agents[] = makeAgent($owner);
        }

        $response = $this->getJson('/api/v1/memories', withAgent($agents[3]));
        $response->assertOk();
    });

    it('allows write on first 3 agents when downgraded', function () {
        $owner = makeOwner();
        $agents = [];
        for ($i = 0; $i < 4; $i++) {
            $agents[] = makeAgent($owner);
        }

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'test memory',
        ], withAgent($agents[0]));

        $response->assertStatus(201);
    });

    it('blocks workspace memory writes when downgraded', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner);
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);
        $agent->workspaces()->attach($workspace->id);

        // Owner is downgraded because they own a workspace but have no Pro sub
        $response = $this->postJson('/api/v1/memories', [
            'value' => 'workspace memory',
            'workspace_id' => $workspace->id,
        ], withAgent($agent));

        $response->assertStatus(403);
        $response->assertJsonFragment(['error' => 'Workspace memories are read-only. Upgrade to Pro to restore write access.']);
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
php artisan test tests/Feature/BillingTest.php --filter="soft lock"
```

Expected: FAIL — no soft lock enforcement yet.

- [ ] **Step 3: Implement soft lock in AuthenticateAgent middleware**

Replace `app/Http/Middleware/AuthenticateAgent.php` entirely. **Important:** The existing `wks_` workspace token branch (lines 23-34) must be preserved.

```php
<?php

namespace App\Http\Middleware;

use App\Models\Agent;
use App\Models\Memory;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class AuthenticateAgent
{
    public function handle(Request $request, Closure $next): Response
    {
        $token = $request->bearerToken();

        if (! $token) {
            return response()->json([
                'error' => 'No agent token provided.',
                'hint' => 'Include your agent token as: Authorization: Bearer amc_...',
            ], 401);
        }

        // Workspace token authentication (preserved from existing code)
        if (str_starts_with($token, 'wks_')) {
            $workspace = \App\Models\Workspace::where('api_token', $token)->first();

            if (! $workspace) {
                return response()->json([
                    'error' => 'Invalid workspace token.',
                ], 401);
            }

            $request->attributes->set('workspace_token', $workspace);
            return $next($request);
        }

        $agent = Agent::query()
            ->where('api_token', $token)
            ->where('is_active', true)
            ->first();

        if (! $agent) {
            return response()->json([
                'error' => 'Invalid or inactive agent token.',
            ], 401);
        }

        $agent->touchLastSeen();

        $request->attributes->set('agent', $agent);

        // Soft-lock check for write operations on memory endpoints
        if ($this->isWriteOperation($request) && $this->isMemoryEndpoint($request)) {
            $user = $agent->owner;

            if ($user && $user->isDowngraded()) {
                $response = $this->enforceSoftLock($request, $agent, $user);
                if ($response) {
                    return $response;
                }
            }
        }

        return $next($request);
    }

    private function isWriteOperation(Request $request): bool
    {
        return in_array($request->method(), ['POST', 'PUT', 'PATCH', 'DELETE']);
    }

    private function isMemoryEndpoint(Request $request): bool
    {
        $path = $request->path();

        return preg_match('#v1/memories($|/)#', $path) === 1;
    }

    private function enforceSoftLock(Request $request, Agent $agent, $user): ?Response
    {
        // Check if this agent is outside the first 3
        $allowedAgentIds = $user->agents()
            ->orderBy('created_at')
            ->limit(3)
            ->pluck('id');

        if (! $allowedAgentIds->contains($agent->id)) {
            return response()->json([
                'error' => 'This agent is in read-only mode. Upgrade to Pro to restore write access.',
            ], 403);
        }

        // Check workspace memory writes
        if ($request->isMethod('POST') && $request->input('workspace_id')) {
            return response()->json([
                'error' => 'Workspace memories are read-only. Upgrade to Pro to restore write access.',
            ], 403);
        }

        // For updates/deletes, check if target memory belongs to a workspace
        if (in_array($request->method(), ['PUT', 'PATCH', 'DELETE'])) {
            $key = $request->route('key');
            if ($key) {
                $memory = Memory::where('agent_id', $agent->id)->where('key', $key)->first();
                if ($memory && $memory->workspace_id) {
                    return response()->json([
                        'error' => 'Workspace memories are read-only. Upgrade to Pro to restore write access.',
                    ], 403);
                }
            }
        }

        return null;
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
php artisan test tests/Feature/BillingTest.php --filter="soft lock"
```

Expected: All PASS.

- [ ] **Step 5: Run full test suite**

```bash
php artisan test
```

Expected: All pass (including existing MemoryApiTest which uses single-agent owners).

- [ ] **Step 6: Commit**

```bash
git add app/Http/Middleware/AuthenticateAgent.php tests/Feature/BillingTest.php
git commit -m "feat(billing): enforce soft lock on downgraded users"
```

---

### Task 6: Webhook Listener for Quota Sync

**Files:**
- Create: `app/Listeners/SyncAgentQuotas.php`
- Modify: `app/Providers/AppServiceProvider.php`
- Test: `tests/Feature/BillingTest.php` (append)

- [ ] **Step 1: Write failing tests for quota sync**

Append to `tests/Feature/BillingTest.php`:

```php
// ---------------------------------------------------------------------------
// Quota Sync
// ---------------------------------------------------------------------------

describe('quota sync', function () {
    it('sets max_memories to 10000 when user subscribes', function () {
        $user = makeOwner(['stripe_id' => 'cus_sync_test']);
        $agent = makeAgent($user);

        expect($agent->fresh()->max_memories)->toBe(1000);

        // Simulate subscription created webhook
        $event = new \Laravel\Cashier\Events\WebhookReceived([
            'type' => 'customer.subscription.created',
            'data' => ['object' => ['customer' => 'cus_sync_test']],
        ]);

        // Before creating subscription, make user Pro
        $subscription = $user->subscriptions()->create([
            'type' => 'default',
            'stripe_id' => 'sub_sync_test',
            'stripe_status' => 'active',
            'stripe_price' => 'price_test',
            'quantity' => 1,
        ]);
        $subscription->items()->create([
            'stripe_id' => 'si_sync_test',
            'stripe_product' => 'prod_test',
            'stripe_price' => 'price_test',
            'quantity' => 1,
        ]);

        $listener = new \App\Listeners\SyncAgentQuotas();
        $listener->handle($event);

        expect($agent->fresh()->max_memories)->toBe(10000);
    });

    it('sets max_memories to 1000 when subscription is deleted', function () {
        $user = makeProUser(['stripe_id' => 'cus_downgrade_test']);
        $agent = makeAgent($user, ['max_memories' => 10000]);

        // Delete the subscription to simulate downgrade
        $user->subscriptions()->delete();

        $event = new \Laravel\Cashier\Events\WebhookReceived([
            'type' => 'customer.subscription.deleted',
            'data' => ['object' => ['customer' => 'cus_downgrade_test']],
        ]);

        $listener = new \App\Listeners\SyncAgentQuotas();
        $listener->handle($event);

        expect($agent->fresh()->max_memories)->toBe(1000);
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
php artisan test tests/Feature/BillingTest.php --filter="quota sync"
```

Expected: FAIL — SyncAgentQuotas class not found.

- [ ] **Step 3: Create SyncAgentQuotas listener**

Create `app/Listeners/SyncAgentQuotas.php`:

```php
<?php

namespace App\Listeners;

use App\Models\User;
use Laravel\Cashier\Events\WebhookReceived;

class SyncAgentQuotas
{
    public function handle(WebhookReceived $event): void
    {
        $payload = $event->payload;
        $type = $payload['type'] ?? null;

        if (! in_array($type, [
            'customer.subscription.created',
            'customer.subscription.updated',
            'customer.subscription.deleted',
        ])) {
            return;
        }

        $stripeId = $payload['data']['object']['customer'] ?? null;
        $user = User::where('stripe_id', $stripeId)->first();

        if (! $user) {
            return;
        }

        $limit = $user->maxMemoriesPerAgent();
        $user->agents()->update(['max_memories' => $limit]);
    }
}
```

- [ ] **Step 4: Register listener in AppServiceProvider**

In `app/Providers/AppServiceProvider.php`, add the import at the top:

```php
use App\Listeners\SyncAgentQuotas;
use Illuminate\Support\Facades\Event;
use Laravel\Cashier\Events\WebhookReceived;
```

Add to the `boot()` method, after the RateLimiter definitions (after line 43):

```php
        Event::listen(WebhookReceived::class, SyncAgentQuotas::class);
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
php artisan test tests/Feature/BillingTest.php --filter="quota sync"
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add app/Listeners/SyncAgentQuotas.php app/Providers/AppServiceProvider.php tests/Feature/BillingTest.php
git commit -m "feat(billing): add webhook listener to sync agent quotas on subscription changes"
```

---

## Chunk 3: Billing Routes & Frontend

### Task 7: BillingController

**Files:**
- Create: `app/Http/Controllers/BillingController.php`
- Modify: `routes/web.php`
- Test: `tests/Feature/BillingTest.php` (append)

- [ ] **Step 1: Write failing tests for billing routes**

Append to `tests/Feature/BillingTest.php`:

```php
// ---------------------------------------------------------------------------
// Billing Routes
// ---------------------------------------------------------------------------

describe('billing routes', function () {
    it('redirects unauthenticated user from checkout to login', function () {
        $this->get('/billing/checkout')
            ->assertRedirect('/login');
    });

    it('redirects unauthenticated user from portal to login', function () {
        $this->get('/billing/portal')
            ->assertRedirect('/login');
    });

    it('renders pricing page for guests', function () {
        $this->get('/pricing')
            ->assertOk();
    });

    it('renders pricing page for authenticated users', function () {
        $user = makeOwner();
        $this->actingAs($user)->get('/pricing')
            ->assertOk();
    });

    it('renders success page for authenticated users', function () {
        $user = makeOwner();
        $this->actingAs($user)->get('/billing/success')
            ->assertRedirect('/dashboard');
    });

    it('creates checkout session for authenticated user', function () {
        Http::fake(['https://api.stripe.com/*' => Http::response(['id' => 'cs_test', 'url' => 'https://checkout.stripe.com/test'], 200)]);

        $user = makeOwner(['stripe_id' => 'cus_checkout_test']);
        $response = $this->actingAs($user)->get('/billing/checkout');
        $response->assertRedirect();
    });

    it('redirects pro user to billing portal', function () {
        Http::fake(['https://api.stripe.com/*' => Http::response(['url' => 'https://billing.stripe.com/portal/test'], 200)]);

        $user = makeProUser();
        $response = $this->actingAs($user)->get('/billing/portal');
        $response->assertRedirect();
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
php artisan test tests/Feature/BillingTest.php --filter="billing routes"
```

Expected: FAIL — routes not registered.

- [ ] **Step 3: Create BillingController**

Create `app/Http/Controllers/BillingController.php`:

```php
<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Inertia\Inertia;

class BillingController extends Controller
{
    public function pricing(Request $request)
    {
        $user = $request->user();

        return Inertia::render('Pricing', [
            'isPro' => $user?->isPro() ?? false,
        ]);
    }

    public function checkout(Request $request)
    {
        $user = $request->user();

        return $user->newSubscription('default', config('stripe.pro_price_id'))
            ->checkout([
                'success_url' => route('billing.success') . '?session_id={CHECKOUT_SESSION_ID}',
                'cancel_url' => route('pricing'),
            ]);
    }

    public function success(Request $request)
    {
        return redirect()->route('dashboard')
            ->with('message', 'Welcome to Pro! Your subscription is active.');
    }

    public function portal(Request $request)
    {
        return $request->user()->redirectToBillingPortal(route('dashboard'));
    }
}
```

- [ ] **Step 4: Add billing routes to routes/web.php**

Add these routes. Insert after line 53 (`Route::post('/logout'...`) and before the closing `});` of the auth group:

```php
    Route::get('/billing/checkout', [BillingController::class, 'checkout'])->name('billing.checkout');
    Route::get('/billing/success', [BillingController::class, 'success'])->name('billing.success');
    Route::get('/billing/portal', [BillingController::class, 'portal'])->name('billing.portal');
```

Add the pricing route after the auth group (after line 54). This is a public route:

```php
Route::get('/pricing', [BillingController::class, 'pricing'])->name('pricing');
```

Add the import at the top of `routes/web.php`:

```php
use App\Http\Controllers\BillingController;
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
php artisan test tests/Feature/BillingTest.php --filter="billing routes"
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add app/Http/Controllers/BillingController.php routes/web.php tests/Feature/BillingTest.php
git commit -m "feat(billing): add BillingController with checkout, success, portal, pricing routes"
```

---

### Task 8: Dashboard Billing Props

**Files:**
- Modify: `app/Http/Controllers/Auth/DashboardController.php:12-19`
- Test: `tests/Feature/BillingTest.php` (append)

- [ ] **Step 1: Write failing test for dashboard billing props**

Append to `tests/Feature/BillingTest.php`:

```php
describe('dashboard billing props', function () {
    it('passes billing props to dashboard for free user', function () {
        $user = makeOwner();
        makeAgent($user);

        $response = $this->actingAs($user)->get('/dashboard');
        $response->assertOk();
        $response->assertInertia(fn ($page) => $page
            ->component('Dashboard')
            ->has('isPro')
            ->has('isDowngraded')
            ->has('isOnGracePeriod')
            ->has('hasPaymentFailure')
            ->has('currentPlan')
            ->has('agentCount')
            ->has('maxAgents')
            ->has('avgMemoriesPerAgent')
            ->has('maxMemoriesPerAgent')
            ->where('isPro', false)
            ->where('currentPlan', 'free')
        );
    });

    it('passes pro billing props to dashboard', function () {
        $user = makeProUser();

        $response = $this->actingAs($user)->get('/dashboard');
        $response->assertOk();
        $response->assertInertia(fn ($page) => $page
            ->component('Dashboard')
            ->where('isPro', true)
            ->where('currentPlan', 'pro')
            ->where('maxAgents', 'unlimited')
        );
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
php artisan test tests/Feature/BillingTest.php --filter="dashboard billing props"
```

Expected: FAIL — dashboard doesn't return billing props.

- [ ] **Step 3: Update DashboardController::show() to pass billing props**

Replace the `show()` method in `app/Http/Controllers/Auth/DashboardController.php` (lines 12-20):

```php
    public function show(Request $request)
    {
        $user = $request->user();

        $agentCount = $user->agents()->count();
        $avgMemories = $agentCount > 0
            ? (int) $user->agents()->withCount('memories')->get()->avg('memories_count')
            : 0;

        return Inertia::render('Dashboard', [
            'apiToken' => $user->api_token,
            'agents' => $user->agents()->select('id', 'name', 'description', 'created_at')->latest()->get(),
            'isPro' => $user->isPro(),
            'isOnGracePeriod' => $user->isOnGracePeriod(),
            'hasPaymentFailure' => $user->hasPaymentFailure(),
            'isDowngraded' => $user->isDowngraded(),
            'currentPlan' => $user->isPro() ? 'pro' : 'free',
            'agentCount' => $agentCount,
            'maxAgents' => $user->isPro() ? 'unlimited' : $user->maxAgents(),
            'avgMemoriesPerAgent' => $avgMemories,
            'maxMemoriesPerAgent' => $user->maxMemoriesPerAgent(),
        ]);
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
php artisan test tests/Feature/BillingTest.php --filter="dashboard billing props"
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add app/Http/Controllers/Auth/DashboardController.php tests/Feature/BillingTest.php
git commit -m "feat(billing): pass billing props to dashboard via Inertia"
```

---

### Task 9: Pricing Page (Vue)

**Files:**
- Create: `resources/js/Pages/Pricing.vue`

- [ ] **Step 1: Create Pricing.vue**

Create `resources/js/Pages/Pricing.vue`:

```vue
<script setup>
import { Link, usePage } from '@inertiajs/vue3';
import AppLayout from '../Layouts/AppLayout.vue';
import { computed } from 'vue';

const props = defineProps({
    isPro: Boolean,
});

const page = usePage();
const user = computed(() => page.props.auth?.user);
</script>

<template>
    <AppLayout>
        <div class="text-center mb-12">
            <h1 class="text-3xl font-bold mb-2">Simple pricing for agent memory</h1>
            <p class="text-gray-400">Free forever for public agents. Pro when you need private workspaces.</p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl mx-auto">
            <!-- Free -->
            <div class="rounded-xl border border-gray-700 bg-gray-800/50 p-7">
                <span class="text-xs font-semibold uppercase tracking-wider text-gray-400">Free</span>
                <div class="mt-4 mb-6">
                    <span class="text-4xl font-extrabold text-white">$0</span>
                    <span class="text-sm text-gray-500">/forever</span>
                </div>

                <Link
                    v-if="!user"
                    href="/login"
                    class="block text-center rounded-lg border border-gray-600 py-2.5 text-sm font-semibold text-gray-300 hover:bg-gray-700 transition"
                >
                    Get Started
                </Link>
                <span
                    v-else-if="!isPro"
                    class="block text-center rounded-lg border border-gray-600 py-2.5 text-sm font-semibold text-gray-500 cursor-default"
                >
                    Current Plan
                </span>
                <span
                    v-else
                    class="block text-center rounded-lg border border-gray-600 py-2.5 text-sm font-semibold text-gray-500 cursor-default"
                >
                    Free Tier
                </span>

                <ul class="mt-6 space-y-2.5 border-t border-gray-700 pt-6 text-sm text-gray-400">
                    <li>&#10003; &nbsp;3 agents</li>
                    <li>&#10003; &nbsp;1,000 memories per agent</li>
                    <li>&#10003; &nbsp;Full semantic search</li>
                    <li>&#10003; &nbsp;Commons access</li>
                    <li>&#10003; &nbsp;MCP + REST API</li>
                    <li>&#10003; &nbsp;Arena access</li>
                    <li class="text-gray-600">&#10007; &nbsp;Private workspaces</li>
                </ul>
            </div>

            <!-- Pro -->
            <div class="relative rounded-xl border border-indigo-500/40 bg-indigo-500/5 p-7">
                <span class="absolute -top-2.5 right-4 rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 px-3 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                    Popular
                </span>
                <span class="text-xs font-semibold uppercase tracking-wider text-indigo-400">Pro</span>
                <div class="mt-4 mb-6">
                    <span class="text-4xl font-extrabold text-white">$49</span>
                    <span class="text-sm text-gray-500">/month</span>
                </div>

                <Link
                    v-if="!user"
                    href="/login"
                    class="block text-center rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition"
                >
                    Upgrade to Pro
                </Link>
                <Link
                    v-else-if="!isPro"
                    href="/billing/checkout"
                    class="block text-center rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition"
                >
                    Upgrade to Pro
                </Link>
                <span
                    v-else
                    class="block text-center rounded-lg bg-indigo-600/50 py-2.5 text-sm font-semibold text-indigo-200 cursor-default"
                >
                    Current Plan
                </span>

                <ul class="mt-6 space-y-2.5 border-t border-indigo-500/20 pt-6 text-sm text-indigo-200">
                    <li>&#10003; &nbsp;<strong class="text-indigo-100">Unlimited</strong> agents</li>
                    <li>&#10003; &nbsp;<strong class="text-indigo-100">10,000</strong> memories per agent</li>
                    <li>&#10003; &nbsp;Full semantic search</li>
                    <li>&#10003; &nbsp;Commons access</li>
                    <li>&#10003; &nbsp;MCP + REST API</li>
                    <li>&#10003; &nbsp;Arena access</li>
                    <li>&#10003; &nbsp;<strong class="text-indigo-100">Private workspaces</strong></li>
                </ul>
            </div>
        </div>

        <p class="text-center mt-8 text-xs text-gray-600">
            Questions? <a href="https://discord.gg/remembr" class="text-indigo-400 hover:text-indigo-300">Join our Discord</a>
        </p>
    </AppLayout>
</template>
```

- [ ] **Step 2: Verify it renders**

```bash
php artisan test tests/Feature/BillingTest.php --filter="renders pricing page"
```

Expected: PASS (tests from Task 7 already cover this).

- [ ] **Step 3: Commit**

```bash
git add resources/js/Pages/Pricing.vue
git commit -m "feat(billing): add Pricing page with Free/Pro comparison cards"
```

---

### Task 10: Dashboard Billing Section (Vue)

**Files:**
- Modify: `resources/js/Pages/Dashboard.vue`

- [ ] **Step 1: Update Dashboard.vue with billing section**

Replace `resources/js/Pages/Dashboard.vue` entirely. The key changes: add billing props, add billing section after the agents list, show conditional banners:

```vue
<script setup>
import { useForm, usePage, router, Link } from '@inertiajs/vue3';
import AppLayout from '../Layouts/AppLayout.vue';
import { ref, computed } from 'vue';

const props = defineProps({
    apiToken: String,
    agents: Array,
    isPro: Boolean,
    isOnGracePeriod: Boolean,
    hasPaymentFailure: Boolean,
    isDowngraded: Boolean,
    currentPlan: String,
    agentCount: Number,
    maxAgents: [Number, String],
    avgMemoriesPerAgent: Number,
    maxMemoriesPerAgent: Number,
});

const page = usePage();
const flash = computed(() => page.props.flash?.message);

const copied = ref(false);
function copyToken(token) {
    navigator.clipboard.writeText(token);
    copied.value = true;
    setTimeout(() => (copied.value = false), 2000);
}

const agentForm = useForm({
    name: '',
    description: '',
});

function registerAgent() {
    agentForm.post('/dashboard/agents', {
        onSuccess: () => agentForm.reset(),
    });
}

function rotateAgentToken(agentId) {
    if (confirm('Are you sure you want to rotate this agent\'s API token? The old token will be immediately invalidated.')) {
        router.post(`/dashboard/agents/${agentId}/rotate`, {}, {
            preserveScroll: true,
        });
    }
}

function deleteAgent(agentId) {
    if (confirm('Are you sure you want to permanently delete this agent? This cannot be undone.')) {
        router.delete(`/dashboard/agents/${agentId}`, {
            preserveScroll: true,
        });
    }
}

function rotateOwnerToken() {
    if (confirm('Are you sure you want to rotate your Owner API token? Any services using the current token will immediately lose access.')) {
        router.post('/dashboard/token/rotate', {}, {
            preserveScroll: true,
        });
    }
}

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

function copyConfig(agent) {
    navigator.clipboard.writeText(getConfigJson(agent));
}

const agentUsagePercent = computed(() => {
    if (props.maxAgents === 'unlimited') return 5;
    return Math.min(100, (props.agentCount / props.maxAgents) * 100);
});

const memoryUsagePercent = computed(() => {
    return Math.min(100, (props.avgMemoriesPerAgent / props.maxMemoriesPerAgent) * 100);
});
</script>

<template>
    <AppLayout>
        <h1 class="text-3xl font-bold mb-8">Dashboard</h1>

        <div v-if="flash" class="mb-6 rounded-lg bg-emerald-900/30 border border-emerald-700/50 px-4 py-3 text-emerald-200 text-sm">
            {{ flash }}
        </div>

        <!-- Billing Banners -->
        <div v-if="hasPaymentFailure" class="mb-6 rounded-lg border border-red-800/50 bg-red-900/20 px-4 py-3 flex items-center gap-2">
            <span class="text-red-400">&#9888;</span>
            <span class="text-sm text-red-200">Payment failed. <a href="/billing/portal" class="text-red-400 underline">Update payment method</a> to keep Pro access.</span>
        </div>

        <div v-if="isOnGracePeriod" class="mb-6 rounded-lg border border-amber-800/50 bg-amber-900/20 px-4 py-3 text-sm text-amber-200">
            Your Pro subscription has been cancelled and will end at the end of the current billing period. <a href="/billing/portal" class="text-amber-400 underline">Resubscribe</a>
        </div>

        <div v-if="isDowngraded" class="mb-6 rounded-lg border border-amber-800/50 bg-amber-900/20 px-4 py-3 text-sm text-amber-200">
            Your account has features beyond the free plan. Some agents and workspace memories are read-only. <Link href="/billing/checkout" class="text-amber-400 underline">Upgrade to Pro</Link> to restore full access.
        </div>

        <!-- Billing Section -->
        <section class="mb-10">
            <div class="rounded-xl border border-gray-700 bg-gray-800/50 p-6">
                <div class="flex items-center justify-between mb-5">
                    <div>
                        <span class="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Current Plan</span>
                        <div class="flex items-center gap-2 mt-1">
                            <span class="text-xl font-bold text-white">{{ currentPlan === 'pro' ? 'Pro' : 'Free' }}</span>
                            <span v-if="isPro" class="text-[10px] font-semibold bg-indigo-500/15 text-indigo-400 px-2 py-0.5 rounded-full">ACTIVE</span>
                            <span v-else-if="isDowngraded" class="text-[10px] font-semibold bg-amber-500/15 text-amber-400 px-2 py-0.5 rounded-full">DOWNGRADED</span>
                        </div>
                    </div>
                    <div>
                        <a v-if="isPro" href="/billing/portal" class="text-xs text-gray-400 border border-gray-600 px-3 py-1.5 rounded-md hover:bg-gray-700 transition">
                            Manage Subscription
                        </a>
                        <Link v-else href="/billing/checkout" class="text-xs font-semibold bg-indigo-600 text-white px-3 py-1.5 rounded-md hover:bg-indigo-500 transition">
                            Upgrade to Pro
                        </Link>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <div class="flex justify-between mb-1.5">
                            <span class="text-xs text-gray-400">Agents</span>
                            <span class="text-xs font-semibold text-gray-200">{{ agentCount }} / {{ maxAgents }}</span>
                        </div>
                        <div class="bg-gray-700 rounded h-1.5 overflow-hidden">
                            <div class="bg-indigo-500 h-full rounded" :style="{ width: agentUsagePercent + '%' }"></div>
                        </div>
                    </div>
                    <div>
                        <div class="flex justify-between mb-1.5">
                            <span class="text-xs text-gray-400">Avg memories/agent</span>
                            <span class="text-xs font-semibold text-gray-200">{{ avgMemoriesPerAgent.toLocaleString() }} / {{ maxMemoriesPerAgent.toLocaleString() }}</span>
                        </div>
                        <div class="bg-gray-700 rounded h-1.5 overflow-hidden">
                            <div class="bg-indigo-500 h-full rounded" :style="{ width: memoryUsagePercent + '%' }"></div>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Owner API Token -->
        <section class="mb-10">
            <h2 class="text-lg font-semibold mb-3 text-gray-200">Your Owner API Token</h2>
            <div class="flex items-center gap-3 rounded-lg border border-gray-700 bg-gray-800 px-4 py-3">
                <code class="flex-1 text-sm text-indigo-300 font-mono break-all">{{ apiToken }}</code>
                <button
                    @click="copyToken(apiToken)"
                    class="shrink-0 rounded bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-200 hover:bg-gray-600 transition"
                >
                    {{ copied ? 'Copied!' : 'Copy' }}
                </button>
                <button
                    @click="rotateOwnerToken"
                    class="shrink-0 rounded border border-gray-600 px-3 py-1.5 text-xs font-medium text-gray-300 hover:text-white hover:bg-gray-700 transition"
                >
                    Rotate
                </button>
            </div>
            <p class="mt-2 text-xs text-gray-500">Use this token to register agents via the API.</p>
        </section>

        <!-- Register Agent -->
        <section class="mb-10">
            <h2 class="text-lg font-semibold mb-3 text-gray-200">Register New Agent</h2>
            <form @submit.prevent="registerAgent" class="space-y-4">
                <div>
                    <label for="agent-name" class="block text-sm font-medium text-gray-300 mb-1">Agent Name</label>
                    <input
                        id="agent-name"
                        v-model="agentForm.name"
                        type="text"
                        required
                        class="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-white placeholder-gray-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
                        placeholder="My Agent"
                    />
                    <p v-if="agentForm.errors.name" class="mt-1 text-sm text-red-400">{{ agentForm.errors.name }}</p>
                </div>
                <div>
                    <label for="agent-desc" class="block text-sm font-medium text-gray-300 mb-1">Description (optional)</label>
                    <input
                        id="agent-desc"
                        v-model="agentForm.description"
                        type="text"
                        class="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-white placeholder-gray-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
                        placeholder="What does this agent do?"
                    />
                </div>
                <button
                    type="submit"
                    :disabled="agentForm.processing"
                    class="rounded-lg bg-indigo-600 px-4 py-2.5 font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition"
                >
                    {{ agentForm.processing ? 'Creating...' : 'Create Agent' }}
                </button>
            </form>
        </section>

        <!-- Agents List -->
        <section>
            <h2 class="text-lg font-semibold mb-3 text-gray-200">Your Agents</h2>
            <div v-if="agents.length === 0" class="text-gray-500 text-sm">
                No agents registered yet.
            </div>
            <div v-else class="space-y-3">
                <div
                    v-for="agent in agents"
                    :key="agent.id"
                    class="rounded-lg border border-gray-700 bg-gray-800/50 px-4 py-3"
                >
                    <div class="flex items-center justify-between">
                        <div class="flex flex-col">
                            <span class="font-medium text-white">{{ agent.name }}</span>
                            <span class="text-xs text-gray-500">{{ new Date(agent.created_at).toLocaleDateString() }}</span>
                        </div>
                        <div class="flex items-center gap-2">
                            <button
                                @click="rotateAgentToken(agent.id)"
                                class="rounded bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-300 hover:text-white hover:bg-gray-600 transition"
                            >
                                Rotate Token
                            </button>
                            <button
                                @click="deleteAgent(agent.id)"
                                class="rounded bg-red-900/40 border border-red-800/50 px-3 py-1.5 text-xs font-medium text-red-400 hover:text-red-200 hover:bg-red-800/60 transition"
                            >
                                Delete
                            </button>
                        </div>
                    </div>
                    <p v-if="agent.description" class="mt-2 text-sm text-gray-400">{{ agent.description }}</p>
                    <div class="mt-3 rounded-lg bg-gray-800/50 p-4">
                        <div class="flex items-center justify-between mb-2">
                            <span class="text-xs font-mono text-gray-400">Claude Desktop / Cursor config</span>
                            <button @click="copyConfig(agent)" class="text-xs text-indigo-400 hover:text-indigo-300 transition">
                                Copy
                            </button>
                        </div>
                        <pre class="text-xs text-gray-300 overflow-x-auto whitespace-pre"><code>{{ getConfigJson(agent) }}</code></pre>
                    </div>
                </div>
            </div>
        </section>
    </AppLayout>
</template>
```

- [ ] **Step 2: Run tests to verify nothing broke**

```bash
php artisan test tests/Feature/BillingTest.php
```

Expected: All PASS. Dashboard billing props tests from Task 8 still pass.

- [ ] **Step 3: Commit**

```bash
git add resources/js/Pages/Dashboard.vue
git commit -m "feat(billing): add billing section to dashboard with usage bars and banners"
```

---

### Task 11: Navigation Updates

**Files:**
- Modify: `resources/js/Layouts/AppLayout.vue:16-35`

- [ ] **Step 1: Add Pricing link to AppLayout navigation**

In `resources/js/Layouts/AppLayout.vue`, add the Pricing link in both the authenticated and guest navigation sections.

For authenticated users (after the Docs link on line 21, before the email span on line 22):

```html
                    <Link href="/pricing" class="text-sm text-gray-400 hover:text-white transition">Pricing</Link>
```

For guest users (after the Docs link on line 31, before the Sign in link on line 32):

```html
                    <Link href="/pricing" class="text-sm text-gray-400 hover:text-white transition">Pricing</Link>
```

- [ ] **Step 2: Commit**

```bash
git add resources/js/Layouts/AppLayout.vue
git commit -m "feat(billing): add Pricing link to navigation"
```

---

### Task 12: .env.example + Final Verification

**Files:**
- None (already done in Task 1)

- [ ] **Step 1: Run full test suite**

```bash
php artisan test
```

Expected: All tests pass (existing tests + new billing tests).

- [ ] **Step 2: Build frontend**

```bash
npm run build
```

Expected: Builds without errors.

- [ ] **Step 3: Final commit if any remaining changes**

```bash
git status
# Only commit if there are uncommitted changes
```
