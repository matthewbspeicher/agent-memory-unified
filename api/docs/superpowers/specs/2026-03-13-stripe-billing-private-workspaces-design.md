# Stripe Billing & Private Workspaces

**Date:** 2026-03-13
**Status:** Final
**Scope:** Subscription tiers (Free/Pro), Stripe Checkout integration, plan enforcement, soft-lock downgrade, pricing page, dashboard billing UI

---

## Problem

Remembr has a fully functional workspace system (workspace-scoped memories, agent membership, visibility controls) but no way to monetize it. All features are free with no billing infrastructure. To turn Remembr into a sustainable business, we need a subscription tier that gates private workspaces behind a paid plan while keeping the public Commons free to drive adoption.

## Solution

Two-tier subscription model (Free / Pro $49/mo) using Laravel Cashier with Stripe Checkout. Free tier drives adoption through the public Commons. Pro tier unlocks private workspaces, unlimited agents, and higher memory quotas. Soft-lock downgrade ensures no data is ever deleted.

---

## 1. Pricing Tiers

| | Free | Pro ($49/mo) |
|---|---|---|
| Agents | 3 | Unlimited |
| Memories per agent | 1,000 | 10,000 |
| Private workspaces | No | Yes |
| Commons access | Full | Full |
| Semantic search | Full | Full |
| MCP + REST API | Full | Full |
| Arena access | Full | Full |

### Design Decisions

- **Free tier is generous intentionally.** 3 agents with 1,000 memories each and full search/commons access is enough to build something real. The upgrade trigger is needing private workspaces or a 4th agent.
- **No Team tier at launch.** Add it when customers ask for multi-user billing. YAGNI.
- **No usage-based pricing.** Flat tiers are simpler to understand, implement, and predict revenue from.
- **No trials.** The free tier IS the trial.

---

## 2. Data Model

### 2.1 Laravel Cashier Tables

Install `laravel/cashier-stripe`. Cashier adds the following via its standard migrations:

**Columns added to `users` table:**
- `stripe_id` VARCHAR — Stripe customer ID (e.g., `cus_...`)
- `pm_type` VARCHAR — Payment method type (e.g., `"card"`)
- `pm_last_four` VARCHAR(4) — Last 4 digits of payment method
- `trial_ends_at` TIMESTAMP nullable — Not used at launch, but Cashier expects it

**New `subscriptions` table** (Cashier migration):
- `id`, `user_id`, `type` (default `"default"`), `stripe_id`, `stripe_status`, `stripe_price`, `quantity`, `trial_ends_at`, `ends_at`, `created_at`, `updated_at`

**New `subscription_items` table** (Cashier migration):
- Standard Cashier table for multi-price subscriptions. We use a single price, but Cashier requires this table.

### 2.2 No Additional Tables

All subscription state derives from Cashier's tables. No custom billing tables needed.

### 2.3 Stripe Configuration

**Products/Prices to create in Stripe Dashboard:**
- Product: "Remembr Pro"
- Price: $49.00/month, recurring

**Environment variables:**
```env
STRIPE_KEY=pk_live_...
STRIPE_SECRET=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRO_PRICE_ID=price_...
```

**Config file** (`config/stripe.php`):
```php
return [
    'pro_price_id' => env('STRIPE_PRO_PRICE_ID'),
];
```

### 2.4 User Model Helpers

Add to `App\Models\User`:

```php
use Laravel\Cashier\Billable;

class User extends Authenticatable
{
    use Billable;

    // Hide Cashier columns from API responses
    protected $hidden = [
        // ...existing hidden fields...
        'stripe_id', 'pm_type', 'pm_last_four', 'trial_ends_at',
    ];

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
}
```

**Note:** `ownedWorkspaces()` is a `hasMany(Workspace::class, 'owner_id')` relationship. Add it if not already present.

**Grace period behavior:** During the grace period (user cancelled but billing period hasn't ended), `isPro()` still returns true via Cashier's `subscribed()` method, which considers grace-period subscriptions as active. All Pro features remain fully accessible until the period ends.

---

## 3. Plan Enforcement

Three server-side enforcement points. All gates are at the controller/middleware layer — no client-side checks.

### 3.1 Agent Creation Cap

There are two agent creation paths — both must enforce the cap.

**File 1:** `app/Http/Controllers/Api/AgentController.php` — `register()` method

After validating the owner token, before creating the agent:

```php
$user = User::where('api_token', $validated['owner_token'])->firstOrFail();

if ($user->agents()->count() >= $user->maxAgents()) {
    abort(403, 'Agent limit reached. Upgrade to Pro for unlimited agents.');
}
```

**File 2:** `app/Http/Controllers/Auth/DashboardController.php` — `registerAgent()` method

Before creating the agent:

```php
$user = $request->user();

if ($user->agents()->count() >= $user->maxAgents()) {
    return back()->withErrors(['name' => 'Agent limit reached. Upgrade to Pro for unlimited agents.']);
}
```

Free users hit this at 3 agents. Pro users never hit it.

### 3.2 Workspace Creation Gate

**File:** `app/Http/Controllers/Api/WorkspaceController.php` — `store()` method

Before creating the workspace:

```php
$user = $agent->owner;

if (!$user->canCreateWorkspace()) {
    abort(403, 'Private workspaces require a Pro subscription.');
}
```

### 3.3 Memory Quota Sync

Agent `max_memories` is updated when subscription status changes (see Section 5 — Webhooks). The existing quota enforcement in `MemoryService::store()` continues to work unchanged — it already checks `$agent->max_memories`.

### 3.4 Soft Lock on Downgrade

When a user was Pro but has cancelled/lapsed, their extra agents and workspace memories become read-only.

**Detection:** `User::isDowngraded()` returns true when the user is not Pro and either has more than 3 agents or owns any workspaces.

**Enforcement in agent auth middleware** (`AuthenticateAgent`):

For write operations (POST/PUT/PATCH/DELETE on memory endpoints):

1. Resolve agent → owner (user) via `$agent->owner`
2. If `$user->isDowngraded()`:
   - Get user's first 3 agents ordered by `created_at`
   - If current agent is NOT in those 3 → `403: "This agent is in read-only mode. Upgrade to Pro to restore write access."`
   - For new memories (POST): check `$request->input('workspace_id')` — if set, block with `403: "Workspace memories are read-only. Upgrade to Pro to restore write access."`
   - For updates/deletes (PUT/PATCH/DELETE): load the target memory — if `$memory->workspace_id` is set, block with same 403
3. Otherwise, proceed normally

**What stays accessible on downgrade:**
- All read operations (search, list, get) — full access
- First 3 agents retain full write access for non-workspace memories (up to 1,000 memory limit)
- All existing data is preserved — nothing is deleted, nothing is removed from workspaces
- Existing memories above the 1,000 quota are preserved but no new writes are allowed (existing `MemoryService::store()` enforces `max_memories`)

---

## 4. Stripe Integration

### 4.1 Checkout Flow (Upgrade)

1. User clicks "Upgrade to Pro" on `/pricing` or dashboard billing tab
2. `GET /billing/checkout` — controller creates a Stripe Checkout Session:
   ```php
   return $user->newSubscription('default', config('stripe.pro_price_id'))
       ->checkout([
           'success_url' => route('billing.success') . '?session_id={CHECKOUT_SESSION_ID}',
           'cancel_url' => route('pricing'),
       ]);
   ```
3. User completes payment on Stripe's hosted checkout page
4. Stripe redirects to `/billing/success`
5. Stripe fires `checkout.session.completed` webhook → Cashier creates local subscription record
6. Custom webhook listener syncs agent quotas to 10,000

### 4.2 Subscription Management (Cancel/Update Card)

1. User clicks "Manage Subscription" on dashboard billing tab
2. `GET /billing/portal` — controller generates Stripe Customer Portal URL:
   ```php
   return $user->redirectToBillingPortal(route('dashboard'));
   ```
3. User manages subscription on Stripe's portal (update card, cancel, view invoices)
4. Cancellation: Stripe fires webhook → Cashier sets `ends_at` → user stays Pro until period ends (grace period)
5. After grace period: subscription expires → soft lock activates

### 4.3 Routes

```php
// routes/web.php — billing routes (auth required)
Route::middleware('auth')->group(function () {
    Route::get('/billing/checkout', [BillingController::class, 'checkout'])->name('billing.checkout');
    Route::get('/billing/success', [BillingController::class, 'success'])->name('billing.success');
    Route::get('/billing/portal', [BillingController::class, 'portal'])->name('billing.portal');
});

// routes/web.php — public
Route::get('/pricing', [BillingController::class, 'pricing'])->name('pricing');
```

The pricing route uses `BillingController::pricing()` so it can pass the correct Inertia props (see Section 6.1): `auth.user`, `isPro`, `currentPeriodEnd`.

**Webhook route:** Cashier registers `POST /stripe/webhook` automatically. Must be excluded from CSRF verification in `bootstrap/app.php`:

```php
// In bootstrap/app.php, inside ->withMiddleware():
$middleware->validateCsrfTokens(except: ['stripe/*']);
```

---

## 5. Webhook Handling

### 5.1 Events

Cashier handles subscription lifecycle automatically. We add one custom listener to sync agent quotas.

| Stripe Event | Cashier Action | Custom Action |
|---|---|---|
| `checkout.session.completed` | Creates subscription record | None (quota sync fires on `customer.subscription.created`) |
| `customer.subscription.created` | Cashier creates local subscription | Sync quotas → 10,000 |
| `customer.subscription.updated` | Updates subscription status | Re-sync quotas based on new status |
| `customer.subscription.deleted` | Marks subscription as ended | Sync quotas → 1,000 |
| `invoice.payment_failed` | Marks as `past_due` | None (dashboard shows banner) |

**Note:** The custom `SyncAgentQuotas` listener hooks into `customer.subscription.*` events (not `checkout.session.completed`). Stripe fires `customer.subscription.created` as part of the checkout flow, which triggers the quota sync.

### 5.2 Quota Sync Listener

**File:** `app/Listeners/SyncAgentQuotas.php`

Listens to `Laravel\Cashier\Events\WebhookReceived`:

```php
public function handle(WebhookReceived $event): void
{
    $payload = $event->payload;
    $type = $payload['type'] ?? null;

    if (!in_array($type, [
        'customer.subscription.created',
        'customer.subscription.updated',
        'customer.subscription.deleted',
    ])) {
        return;
    }

    $stripeId = $payload['data']['object']['customer'] ?? null;
    $user = User::where('stripe_id', $stripeId)->first();

    if (!$user) return;

    $limit = $user->maxMemoriesPerAgent();
    $user->agents()->update(['max_memories' => $limit]);
}
```

### 5.3 Webhook Security

- Cashier verifies Stripe webhook signatures using `STRIPE_WEBHOOK_SECRET`
- The webhook route is excluded from CSRF protection
- No additional verification needed — Cashier handles this

### 5.4 Payment Failure Flow

Stripe retries failed payments over ~3 weeks (configurable in Stripe Dashboard). During this period:
- Subscription remains active (Cashier status: `past_due`)
- Dashboard shows a warning banner: "Payment failed. Update payment method to keep Pro access."
- Banner links to Stripe Customer Portal for card update
- If all retries fail, Stripe fires `customer.subscription.deleted` → soft lock activates

---

## 6. Frontend

### 6.1 Pricing Page

**File:** `resources/js/Pages/Pricing.vue`
**Route:** `GET /pricing` (public, no auth required)

Two-card layout matching Remembr's dark theme:
- **Free card** — dark border, feature list with checks, "Get Started" button → `/login`
- **Pro card** — indigo border/accent, "Popular" badge, highlighted differences (Unlimited agents, 10,000 memories, Private workspaces), "Upgrade to Pro" button → `/billing/checkout` (or `/login` if not authenticated)

**Server-side props passed via Inertia:**
- `auth.user` — current user (null if guest)
- `isPro` — boolean, current subscription status
- `currentPeriodEnd` — if subscribed, when current period ends

**Button states:**
- Guest: "Get Started" → `/login`, "Upgrade to Pro" → `/login`
- Free user: "Current Plan" (disabled), "Upgrade to Pro" → `/billing/checkout`
- Pro user: "Upgrade to Pro" becomes "Current Plan" (disabled)

### 6.2 Dashboard Billing Tab

**File:** `resources/js/Pages/Dashboard.vue` — new section added below existing agent management

**Plan status card:**
- Current plan name + status badge (Active / Grace Period / Past Due / Free)
- "Manage Subscription" button → `/billing/portal` (Pro users only)
- "Upgrade to Pro" button (Free users only) → `/billing/checkout`

**Usage bars:**
- Agents: `{count} / {max}` with progress bar
- Avg memories per agent: `{avg} / {max}` with progress bar

**Conditional banners:**
- Payment failed (past_due): red warning with link to update payment method
- Grace period: amber notice with days remaining
- Downgraded: amber notice explaining read-only state with upgrade CTA

**Server-side props added to dashboard Inertia response:**
- `isPro` — boolean
- `isOnGracePeriod` — boolean
- `hasPaymentFailure` — boolean
- `isDowngraded` — boolean
- `currentPlan` — `'free'` or `'pro'`
- `agentCount` — integer
- `maxAgents` — integer or `'unlimited'`
- `avgMemoriesPerAgent` — integer
- `maxMemoriesPerAgent` — integer

### 6.3 Navigation Updates

**File:** `resources/js/Layouts/AppLayout.vue`

Add "Pricing" link to the navigation bar (between Docs and Sign in for guests, between Docs and Dashboard for authenticated users).

### 6.4 Landing Page CTA

**File:** `resources/js/Pages/Home.vue`

No changes needed — the existing "Get Started Free" button already links to `/login`.

---

## 7. Files to Create/Modify

### New Files
- `app/Http/Controllers/BillingController.php` — checkout, success, portal actions
- `app/Listeners/SyncAgentQuotas.php` — quota sync on subscription changes
- `config/stripe.php` — Pro price ID config
- `resources/js/Pages/Pricing.vue` — public pricing page
- `database/migrations/XXXX_add_cashier_columns.php` — Cashier's standard migration (via `php artisan vendor:publish --tag=cashier-migrations`)
- `tests/Feature/BillingTest.php` — subscription and enforcement tests

### Modified Files
- `composer.json` — add `laravel/cashier-stripe`
- `.env.example` — add `STRIPE_KEY`, `STRIPE_SECRET`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`
- `app/Models/User.php` — add `Billable` trait, plan helper methods
- `app/Http/Controllers/Api/AgentController.php` — agent creation cap (API path)
- `app/Http/Controllers/Auth/DashboardController.php` — agent creation cap (web UI path)
- `app/Http/Controllers/Api/WorkspaceController.php` — workspace creation gate
- `app/Http/Middleware/AuthenticateAgent.php` — soft lock check for write operations
- `app/Providers/AppServiceProvider.php` — register `SyncAgentQuotas` listener (no EventServiceProvider in this project)
- `routes/web.php` — billing routes + pricing route
- `bootstrap/app.php` — exclude webhook route from CSRF
- `resources/js/Pages/Dashboard.vue` — billing tab section
- `resources/js/Layouts/AppLayout.vue` — pricing nav link
- `app/Http/Controllers/Auth/DashboardController.php` — pass billing props to Inertia

---

## 8. Testing

All tests in `tests/Feature/BillingTest.php` following existing Pest conventions.

### 8.1 Plan Helper Tests
- `isPro()` returns false for unsubscribed user
- `isPro()` returns true for subscribed user
- `maxAgents()` returns 3 for free, PHP_INT_MAX for Pro
- `maxMemoriesPerAgent()` returns 1000 for free, 10000 for Pro
- `canCreateWorkspace()` returns false for free, true for Pro
- `isDowngraded()` returns true when not Pro but has >3 agents
- `isDowngraded()` returns true when not Pro but owns workspaces (even with ≤3 agents)

### 8.2 Agent Cap Enforcement
- Free user can register 3 agents (success)
- Free user gets 403 on 4th agent registration
- Pro user can register unlimited agents

### 8.3 Workspace Gate
- Free user gets 403 on workspace creation
- Pro user can create workspaces

### 8.4 Quota Sync
- Simulated subscription creation sets agent `max_memories` to 10,000
- Simulated subscription deletion sets agent `max_memories` to 1,000

### 8.5 Soft Lock
- Downgraded user's 4th agent returns 403 on memory store
- Downgraded user's 4th agent can still read/search memories
- Downgraded user's first 3 agents retain full write access
- Workspace memory writes return 403 when downgraded

### 8.6 Route Tests
- `GET /billing/checkout` redirects unauthenticated users to login
- `GET /billing/checkout` creates Stripe Checkout Session for authenticated user
- `GET /billing/portal` redirects to Stripe Customer Portal
- `GET /pricing` renders for guests and authenticated users

### 8.7 Mocking Strategy

No real Stripe charges in any test. Two approaches for simulating Pro status:

**Approach 1 — Database seeding (preferred for integration tests):**
Create subscription records directly in the database. Add a helper function or factory state:

```php
// In tests/TestCase.php or a test helper
function makeProUser(): User
{
    $user = User::factory()->create(['stripe_id' => 'cus_test_' . Str::random(10)]);

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

    return $user;
}
```

This makes `$user->subscribed('default')` return true without any Stripe API calls.

**Approach 2 — HTTP mocking (for checkout/portal route tests):**
Use `Http::fake()` to mock Stripe API responses when testing the BillingController routes that actually call Stripe.

**No `Cashier::fake()` exists.** Do not use it.

---

## 9. Deployment Considerations

### 9.1 Stripe Setup (Manual)
1. Create "Remembr Pro" product in Stripe Dashboard
2. Add $49/mo recurring price
3. Configure Customer Portal (allow cancellation, card updates)
4. Set up webhook endpoint pointing to `https://remembr.dev/stripe/webhook`
5. Copy keys to production `.env`

### 9.2 Migration Order
1. `composer require laravel/cashier-stripe`
2. Publish and run Cashier migrations
3. Deploy code changes
4. Verify webhook connectivity with `stripe trigger checkout.session.completed`

### 9.3 Existing Users
- All existing users start on Free tier (no `stripe_id`, no subscription)
- Existing agents keep their current `max_memories` value (1,000 from default)
- No data migration needed — absence of subscription = Free tier
