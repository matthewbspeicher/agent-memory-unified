# Trading Integration Expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 9 features to the trading vertical — trade webhook events, annotations/tags, watchlists/alerts, copy-trading signals, risk metrics, correlations, export, replay/simulation, and multi-agent portfolio — to complete the TurboQuant integration surface.

**Architecture:** Each feature builds on the existing trading CRUD (TradingController, TradingService, TradeObserver) and webhook system (WebhookSubscription, DispatchWebhook, TriggerWebhooks). New features are additive — new migrations, controllers, services, and routes. The TradeObserver is the central dispatch point for trade events.

**Tech Stack:** Laravel 12 / PHP 8.3 / PostgreSQL + pgvector / Pest tests / Python SDK (sdk-python/)

---

## File Map

### Phase 1: Trade Webhook Events
- Modify: `app/Observers/TradeObserver.php` — fire trade events
- Create: `app/Events/TradeOpened.php`
- Create: `app/Events/TradeClosed.php`
- Create: `app/Events/PositionChanged.php`
- Modify: `app/Listeners/TriggerWebhooks.php` — handle trade events
- Modify: `app/Providers/AppServiceProvider.php` — register listeners
- Test: `tests/Feature/TradeWebhookTest.php`

### Phase 2: Trade Annotations/Tags
- Create: `database/migrations/2026_04_01_000001_add_tags_to_trades_table.php`
- Modify: `app/Models/Trade.php` — add tags field
- Modify: `app/Http/Controllers/Api/TradingController.php` — accept/filter tags
- Modify: `database/factories/TradeFactory.php` — add tags state
- Test: `tests/Feature/TradeTagsTest.php`

### Phase 3: Watchlists & Alerts
- Create: `database/migrations/2026_04_01_000002_create_trade_alerts_table.php`
- Create: `app/Models/TradeAlert.php`
- Create: `app/Http/Controllers/Api/TradeAlertController.php`
- Create: `app/Listeners/EvaluateTradeAlerts.php`
- Modify: `app/Providers/AppServiceProvider.php` — register alert listener
- Modify: `routes/api.php` — alert routes
- Test: `tests/Feature/TradeAlertTest.php`

### Phase 4: Copy-Trading Signals Feed
- Create: `database/migrations/2026_04_01_000003_add_signal_broadcasting_to_agents_table.php`
- Create: `app/Http/Controllers/Api/SignalController.php`
- Create: `app/Events/SignalBroadcast.php`
- Modify: `app/Observers/TradeObserver.php` — broadcast signals
- Modify: `routes/api.php` — signal routes
- Test: `tests/Feature/SignalFeedTest.php`

### Phase 5: Risk Metrics on Positions
- Create: `database/migrations/2026_04_01_000004_add_risk_fields_to_positions_table.php`
- Create: `app/Http/Controllers/Api/RiskController.php`
- Create: `app/Services/RiskService.php`
- Modify: `routes/api.php` — risk routes
- Test: `tests/Feature/RiskMetricsTest.php`

### Phase 6: Correlation Endpoint
- Modify: `app/Http/Controllers/Api/TradingStatsController.php` — add correlations method
- Modify: `routes/api.php` — correlations route
- Test: `tests/Feature/TradeCorrelationTest.php`

### Phase 7: Export Endpoints
- Create: `app/Http/Controllers/Api/TradeExportController.php`
- Modify: `routes/api.php` — export routes
- Test: `tests/Feature/TradeExportTest.php`

### Phase 8: Trade Replay/Simulation
- Create: `app/Services/ReplayService.php`
- Create: `app/Http/Controllers/Api/ReplayController.php`
- Modify: `routes/api.php` — replay routes
- Test: `tests/Feature/TradeReplayTest.php`

### Phase 9: Multi-Agent Portfolio View
- Create: `app/Http/Controllers/Api/PortfolioController.php`
- Modify: `routes/api.php` — portfolio routes
- Test: `tests/Feature/MultiAgentPortfolioTest.php`

### Python SDK Updates (after all PHP tasks)
- Modify: `sdk-python/remembr/models.py` — new dataclasses
- Modify: `sdk-python/remembr/trading.py` — new methods
- Create: `sdk-python/remembr/signals.py` — signal feed client
- Create: `sdk-python/remembr/risk.py` — risk client
- Create: `sdk-python/remembr/replay.py` — replay client
- Test: `sdk-python/tests/test_signals.py`
- Test: `sdk-python/tests/test_risk.py`
- Test: `sdk-python/tests/test_replay.py`

---

## Phase 1: Trade Webhook Events

### Task 1: Create Trade Event Classes

**Files:**
- Create: `app/Events/TradeOpened.php`
- Create: `app/Events/TradeClosed.php`
- Create: `app/Events/PositionChanged.php`

- [ ] **Step 1: Create TradeOpened event**

```php
<?php

namespace App\Events;

use App\Models\Trade;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class TradeOpened
{
    use Dispatchable, SerializesModels;

    public function __construct(
        public Trade $trade,
    ) {}
}
```

Write this to `app/Events/TradeOpened.php`.

- [ ] **Step 2: Create TradeClosed event**

```php
<?php

namespace App\Events;

use App\Models\Trade;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class TradeClosed
{
    use Dispatchable, SerializesModels;

    public function __construct(
        public Trade $trade,
    ) {}
}
```

Write this to `app/Events/TradeClosed.php`.

- [ ] **Step 3: Create PositionChanged event**

```php
<?php

namespace App\Events;

use App\Models\Agent;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class PositionChanged
{
    use Dispatchable, SerializesModels;

    public function __construct(
        public Agent $agent,
        public string $ticker,
        public bool $paper,
    ) {}
}
```

Write this to `app/Events/PositionChanged.php`.

- [ ] **Step 4: Commit**

```bash
git add app/Events/TradeOpened.php app/Events/TradeClosed.php app/Events/PositionChanged.php
git commit -m "feat(trading): add TradeOpened, TradeClosed, PositionChanged events"
```

### Task 2: Fire Trade Events from TradeObserver

**Files:**
- Modify: `app/Observers/TradeObserver.php`

- [ ] **Step 1: Write the failing test**

Create `tests/Feature/TradeWebhookTest.php`:

```php
<?php

use App\Events\TradeOpened;
use App\Events\TradeClosed;
use App\Events\PositionChanged;
use App\Models\Agent;
use App\Models\Trade;
use Illuminate\Support\Facades\Event;

beforeEach(function () {
    $this->agent = Agent::factory()->create();
});

it('fires TradeOpened when a parent entry trade is created', function () {
    Event::fake([TradeOpened::class, PositionChanged::class]);

    $response = $this->postJson('/api/v1/trading/trades', [
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '150.00',
        'quantity' => '10',
        'entry_at' => now()->toIso8601String(),
    ], ['Authorization' => "Bearer {$this->agent->api_token}"]);

    $response->assertCreated();

    Event::assertDispatched(TradeOpened::class, function ($event) {
        return $event->trade->ticker === 'AAPL';
    });

    Event::assertDispatched(PositionChanged::class, function ($event) {
        return $event->ticker === 'AAPL';
    });
});

it('fires TradeClosed when a parent trade is fully closed', function () {
    Event::fake([TradeClosed::class, TradeOpened::class, PositionChanged::class]);

    $parent = Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'TSLA',
        'direction' => 'long',
        'entry_price' => '200.00',
        'quantity' => '5',
        'status' => 'open',
        'paper' => true,
    ]);

    $this->postJson('/api/v1/trading/trades', [
        'ticker' => 'TSLA',
        'direction' => 'short',
        'entry_price' => '220.00',
        'quantity' => '5',
        'entry_at' => now()->toIso8601String(),
        'parent_trade_id' => $parent->id,
    ], ['Authorization' => "Bearer {$this->agent->api_token}"]);

    Event::assertDispatched(TradeClosed::class, function ($event) use ($parent) {
        return $event->trade->id === $parent->id;
    });
});

it('does not fire TradeClosed on partial exit', function () {
    Event::fake([TradeClosed::class, TradeOpened::class, PositionChanged::class]);

    $parent = Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'GOOG',
        'direction' => 'long',
        'entry_price' => '100.00',
        'quantity' => '10',
        'status' => 'open',
        'paper' => true,
    ]);

    $this->postJson('/api/v1/trading/trades', [
        'ticker' => 'GOOG',
        'direction' => 'short',
        'entry_price' => '110.00',
        'quantity' => '3',
        'entry_at' => now()->toIso8601String(),
        'parent_trade_id' => $parent->id,
    ], ['Authorization' => "Bearer {$this->agent->api_token}"]);

    Event::assertNotDispatched(TradeClosed::class);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/TradeWebhookTest.php --filter="fires TradeOpened" -v`
Expected: FAIL — TradeOpened not dispatched

- [ ] **Step 3: Modify TradeObserver to fire events**

In `app/Observers/TradeObserver.php`, add imports and event dispatching:

Add to the top imports:
```php
use App\Events\TradeOpened;
use App\Events\TradeClosed;
use App\Events\PositionChanged;
```

Modify the `created` method. Current code recalculates position and processes child trades. Add event dispatching after existing logic:

```php
public function created(Trade $trade): void
{
    if ($trade->parent_trade_id) {
        $parent = $trade->parentTrade;
        $this->tradingService->processChildTrade($trade, $parent);
        RecalculateTradingStats::dispatch($trade->agent, $trade->paper);

        // Fire TradeClosed if parent is now closed
        $parent->refresh();
        if ($parent->status === 'closed') {
            TradeClosed::dispatch($parent);
        }
    } else {
        // New parent entry trade
        TradeOpened::dispatch($trade);
    }

    $this->tradingService->recalculatePosition(
        $trade->agent,
        $trade->ticker,
        $trade->paper,
    );

    PositionChanged::dispatch($trade->agent, $trade->ticker, $trade->paper);

    $this->achievementService->check($trade->agent, 'trade');
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradeWebhookTest.php -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/Observers/TradeObserver.php tests/Feature/TradeWebhookTest.php
git commit -m "feat(trading): fire TradeOpened, TradeClosed, PositionChanged events from observer"
```

### Task 3: Wire Trade Events to Webhook Dispatch

**Files:**
- Modify: `app/Listeners/TriggerWebhooks.php`
- Modify: `app/Providers/AppServiceProvider.php`

- [ ] **Step 1: Write the failing test**

Add to `tests/Feature/TradeWebhookTest.php`:

```php
use App\Models\WebhookSubscription;
use App\Jobs\DispatchWebhook;
use Illuminate\Support\Facades\Queue;

it('dispatches webhook job when trade.opened event fires and agent has subscription', function () {
    Queue::fake();

    $subscriber = Agent::factory()->create();
    WebhookSubscription::create([
        'agent_id' => $subscriber->id,
        'url' => 'https://example.com/hook',
        'events' => ['trade.opened'],
        'secret' => 'test-secret',
        'is_active' => true,
    ]);

    $trade = Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'status' => 'open',
        'paper' => false,
    ]);

    // Manually share the trade publicly by making agent listed
    $this->agent->update(['is_listed' => true]);

    TradeOpened::dispatch($trade);

    Queue::assertPushed(DispatchWebhook::class);
});

it('does not dispatch webhook for paper trades', function () {
    Queue::fake();

    $subscriber = Agent::factory()->create();
    WebhookSubscription::create([
        'agent_id' => $subscriber->id,
        'url' => 'https://example.com/hook',
        'events' => ['trade.opened'],
        'secret' => 'test-secret',
        'is_active' => true,
    ]);

    $trade = Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'paper' => true,
    ]);

    $this->agent->update(['is_listed' => true]);

    TradeOpened::dispatch($trade);

    Queue::assertNothingPushed();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/TradeWebhookTest.php --filter="dispatches webhook" -v`
Expected: FAIL — no listener registered for TradeOpened

- [ ] **Step 3: Add trade event handling to TriggerWebhooks listener**

In `app/Listeners/TriggerWebhooks.php`, the listener currently only handles `MemoryShared`. Modify it to also handle trade events. Add a new method:

```php
use App\Events\TradeOpened;
use App\Events\TradeClosed;
use App\Events\PositionChanged;
```

Add these methods to the TriggerWebhooks class:

```php
public function handleTradeOpened(TradeOpened $event): void
{
    $this->dispatchTradeWebhooks('trade.opened', $event->trade);
}

public function handleTradeClosed(TradeClosed $event): void
{
    $this->dispatchTradeWebhooks('trade.closed', $event->trade);
}

public function handlePositionChanged(PositionChanged $event): void
{
    $subscriptions = WebhookSubscription::where('is_active', true)
        ->whereJsonContains('events', 'position.changed')
        ->get();

    foreach ($subscriptions as $sub) {
        $position = \App\Models\Position::where('agent_id', $event->agent->id)
            ->where('ticker', $event->ticker)
            ->where('paper', $event->paper)
            ->first();

        DispatchWebhook::dispatch($sub, [
            'id' => (string) Str::uuid(),
            'event' => 'position.changed',
            'timestamp' => now()->toIso8601String(),
            'data' => [
                'agent_id' => $event->agent->id,
                'agent_name' => $event->agent->name,
                'ticker' => $event->ticker,
                'paper' => $event->paper,
                'quantity' => $position?->quantity ?? '0',
                'avg_entry_price' => $position?->avg_entry_price ?? '0',
            ],
        ]);
    }
}

private function dispatchTradeWebhooks(string $eventName, Trade $trade): void
{
    // Only broadcast live trades from listed agents
    if ($trade->paper || ! $trade->agent->is_listed) {
        return;
    }

    $subscriptions = WebhookSubscription::where('is_active', true)
        ->whereJsonContains('events', $eventName)
        ->get();

    foreach ($subscriptions as $sub) {
        DispatchWebhook::dispatch($sub, [
            'id' => (string) Str::uuid(),
            'event' => $eventName,
            'timestamp' => now()->toIso8601String(),
            'data' => [
                'trade_id' => $trade->id,
                'agent_id' => $trade->agent_id,
                'agent_name' => $trade->agent->name,
                'ticker' => $trade->ticker,
                'direction' => $trade->direction,
                'quantity' => $trade->quantity,
                'entry_price' => $trade->entry_price,
                'exit_price' => $trade->exit_price,
                'pnl' => $trade->pnl,
                'pnl_percent' => $trade->pnl_percent,
                'strategy' => $trade->strategy,
                'status' => $trade->status,
            ],
        ]);
    }
}
```

Add the `use Illuminate\Support\Str;` and `use App\Models\Trade;` imports at top.

- [ ] **Step 4: Register trade event listeners in AppServiceProvider**

In `app/Providers/AppServiceProvider.php`, find the existing event listener registration. Add:

```php
use App\Events\TradeOpened;
use App\Events\TradeClosed;
use App\Events\PositionChanged;
use App\Listeners\TriggerWebhooks;

// Inside boot() or the Event::listen calls:
Event::listen(TradeOpened::class, [TriggerWebhooks::class, 'handleTradeOpened']);
Event::listen(TradeClosed::class, [TriggerWebhooks::class, 'handleTradeClosed']);
Event::listen(PositionChanged::class, [TriggerWebhooks::class, 'handlePositionChanged']);
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradeWebhookTest.php -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Run full test suite for regression**

Run: `php artisan test tests/Feature/TradingApiTest.php -v`
Expected: All existing tests still PASS

- [ ] **Step 7: Commit**

```bash
git add app/Listeners/TriggerWebhooks.php app/Providers/AppServiceProvider.php tests/Feature/TradeWebhookTest.php
git commit -m "feat(trading): wire trade events to webhook dispatch system"
```

### Task 4: Allow subscribing to trade events via webhook API

**Files:**
- Modify: `app/Http/Controllers/Api/WebhookController.php`

- [ ] **Step 1: Write the failing test**

Add to `tests/Feature/TradeWebhookTest.php`:

```php
it('allows subscribing to trade events via webhook API', function () {
    $response = $this->postJson('/api/v1/webhooks', [
        'url' => 'https://example.com/trade-hook',
        'events' => ['trade.opened', 'trade.closed', 'position.changed'],
    ], ['Authorization' => "Bearer {$this->agent->api_token}"]);

    $response->assertCreated();
    expect($response->json('data.events'))->toContain('trade.opened', 'trade.closed', 'position.changed');
});

it('rejects invalid trade event names', function () {
    $response = $this->postJson('/api/v1/webhooks', [
        'url' => 'https://example.com/hook',
        'events' => ['trade.invalid'],
    ], ['Authorization' => "Bearer {$this->agent->api_token}"]);

    $response->assertUnprocessable();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/TradeWebhookTest.php --filter="allows subscribing to trade events" -v`
Expected: FAIL — validation rejects trade.opened as invalid event

- [ ] **Step 3: Update WebhookController validation**

In `app/Http/Controllers/Api/WebhookController.php`, find the `store` method's validation rule for `events`. Change the `in:` rule to include trade events:

```php
'events.*' => 'required|string|in:memory.shared,memory.semantic_match,trade.opened,trade.closed,position.changed',
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradeWebhookTest.php -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/Http/Controllers/Api/WebhookController.php tests/Feature/TradeWebhookTest.php
git commit -m "feat(trading): allow webhook subscriptions to trade events"
```

---

## Phase 2: Trade Annotations/Tags

### Task 5: Add Tags Column to Trades

**Files:**
- Create: `database/migrations/2026_04_01_000001_add_tags_to_trades_table.php`
- Modify: `app/Models/Trade.php`

- [ ] **Step 1: Create migration**

Run: `php artisan make:migration add_tags_to_trades_table --table=trades`

Replace contents with:

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('trades', function (Blueprint $table) {
            $table->jsonb('tags')->nullable()->after('metadata');
        });

        // GIN index for fast jsonb array containment queries
        DB::statement('CREATE INDEX trades_tags_gin ON trades USING GIN (tags jsonb_path_ops)');
    }

    public function down(): void
    {
        Schema::table('trades', function (Blueprint $table) {
            $table->dropColumn('tags');
        });
    }
};
```

- [ ] **Step 2: Run migration**

Run: `php artisan migrate`
Expected: Migration runs successfully

- [ ] **Step 3: Update Trade model**

In `app/Models/Trade.php`, add `'tags'` to the `$fillable` array and add to `$casts`:

```php
// In $casts:
'tags' => 'array',
```

- [ ] **Step 4: Commit**

```bash
git add database/migrations/*add_tags_to_trades_table.php app/Models/Trade.php
git commit -m "feat(trading): add tags jsonb column to trades table"
```

### Task 6: Accept and Filter Tags in TradingController

**Files:**
- Modify: `app/Http/Controllers/Api/TradingController.php`
- Create: `tests/Feature/TradeTagsTest.php`

- [ ] **Step 1: Write the failing test**

Create `tests/Feature/TradeTagsTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\Trade;

beforeEach(function () {
    $this->agent = Agent::factory()->create();
    $this->headers = ['Authorization' => "Bearer {$this->agent->api_token}"];
});

it('accepts tags when creating a trade', function () {
    $response = $this->postJson('/api/v1/trading/trades', [
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '150.00',
        'quantity' => '10',
        'entry_at' => now()->toIso8601String(),
        'tags' => ['earnings-play', 'momentum'],
    ], $this->headers);

    $response->assertCreated();
    expect($response->json('data.tags'))->toBe(['earnings-play', 'momentum']);
});

it('filters trades by tag', function () {
    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'AAPL',
        'tags' => ['momentum', 'tech'],
        'paper' => true,
    ]);
    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'TSLA',
        'tags' => ['earnings-play'],
        'paper' => true,
    ]);

    $response = $this->getJson('/api/v1/trading/trades?tag=momentum', $this->headers);

    $response->assertOk();
    expect($response->json('data'))->toHaveCount(1);
    expect($response->json('data.0.ticker'))->toBe('AAPL');
});

it('allows updating tags on an existing trade', function () {
    $trade = Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'tags' => ['old-tag'],
    ]);

    $response = $this->patchJson("/api/v1/trading/trades/{$trade->id}", [
        'tags' => ['new-tag', 'updated'],
    ], $this->headers);

    $response->assertOk();
    expect($response->json('data.tags'))->toBe(['new-tag', 'updated']);
});

it('validates tags are strings', function () {
    $response = $this->postJson('/api/v1/trading/trades', [
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '150.00',
        'quantity' => '10',
        'entry_at' => now()->toIso8601String(),
        'tags' => [123, true],
    ], $this->headers);

    $response->assertUnprocessable();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/TradeTagsTest.php --filter="accepts tags" -v`
Expected: FAIL — tags not in validation rules

- [ ] **Step 3: Add tags to TradingController store and index**

In `app/Http/Controllers/Api/TradingController.php`:

**store method** — add validation rule:
```php
'tags' => 'nullable|array|max:20',
'tags.*' => 'string|max:50',
```

And include `'tags'` in the `$validated` array passed to `Trade::create()`.

**index method** — add tag filter after existing filters:
```php
if ($request->has('tag')) {
    $query->whereJsonContains('tags', $request->input('tag'));
}
```

**update method** — add `'tags'` to the mutable fields validation:
```php
'tags' => 'nullable|array|max:20',
'tags.*' => 'string|max:50',
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradeTagsTest.php -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run existing tests for regression**

Run: `php artisan test tests/Feature/TradingApiTest.php -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/Http/Controllers/Api/TradingController.php tests/Feature/TradeTagsTest.php
git commit -m "feat(trading): accept and filter tags on trades"
```

---

## Phase 3: Watchlists & Alerts

### Task 7: Create TradeAlert Model and Migration

**Files:**
- Create: `database/migrations/2026_04_01_000002_create_trade_alerts_table.php`
- Create: `app/Models/TradeAlert.php`

- [ ] **Step 1: Create migration**

Run: `php artisan make:migration create_trade_alerts_table`

Replace contents:

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('trade_alerts', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('agent_id')->constrained()->cascadeOnDelete();
            $table->string('ticker', 64)->nullable();          // null = all tickers
            $table->string('condition');                         // pnl_above, pnl_below, trade_opened, trade_closed
            $table->decimal('threshold', 24, 8)->nullable();    // for pnl conditions
            $table->string('delivery', 20)->default('webhook'); // webhook or poll
            $table->boolean('is_active')->default(true);
            $table->integer('trigger_count')->default(0);
            $table->timestamp('last_triggered_at')->nullable();
            $table->timestamps();

            $table->index(['agent_id', 'is_active']);
            $table->index(['ticker', 'condition', 'is_active']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('trade_alerts');
    }
};
```

- [ ] **Step 2: Create TradeAlert model**

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class TradeAlert extends Model
{
    use HasUuids;

    public const CONDITIONS = [
        'pnl_above',
        'pnl_below',
        'trade_opened',
        'trade_closed',
    ];

    protected $fillable = [
        'agent_id',
        'ticker',
        'condition',
        'threshold',
        'delivery',
        'is_active',
        'trigger_count',
        'last_triggered_at',
    ];

    protected $casts = [
        'threshold' => 'decimal:8',
        'is_active' => 'boolean',
        'last_triggered_at' => 'datetime',
    ];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }
}
```

- [ ] **Step 3: Run migration**

Run: `php artisan migrate`
Expected: Migration runs successfully

- [ ] **Step 4: Commit**

```bash
git add database/migrations/*create_trade_alerts_table.php app/Models/TradeAlert.php
git commit -m "feat(trading): add trade_alerts table and model"
```

### Task 8: TradeAlert CRUD Controller

**Files:**
- Create: `app/Http/Controllers/Api/TradeAlertController.php`
- Modify: `routes/api.php`
- Create: `tests/Feature/TradeAlertTest.php`

- [ ] **Step 1: Write the failing test**

Create `tests/Feature/TradeAlertTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\TradeAlert;

beforeEach(function () {
    $this->agent = Agent::factory()->create();
    $this->headers = ['Authorization' => "Bearer {$this->agent->api_token}"];
});

it('creates a trade alert', function () {
    $response = $this->postJson('/api/v1/trading/alerts', [
        'ticker' => 'AAPL',
        'condition' => 'pnl_above',
        'threshold' => '500.00',
    ], $this->headers);

    $response->assertCreated();
    expect($response->json('data.ticker'))->toBe('AAPL');
    expect($response->json('data.condition'))->toBe('pnl_above');
});

it('creates a wildcard alert for all tickers', function () {
    $response = $this->postJson('/api/v1/trading/alerts', [
        'condition' => 'trade_closed',
    ], $this->headers);

    $response->assertCreated();
    expect($response->json('data.ticker'))->toBeNull();
});

it('lists alerts for the agent', function () {
    TradeAlert::create([
        'agent_id' => $this->agent->id,
        'condition' => 'trade_opened',
        'is_active' => true,
    ]);

    $response = $this->getJson('/api/v1/trading/alerts', $this->headers);

    $response->assertOk();
    expect($response->json('data'))->toHaveCount(1);
});

it('deletes an alert', function () {
    $alert = TradeAlert::create([
        'agent_id' => $this->agent->id,
        'condition' => 'trade_opened',
    ]);

    $response = $this->deleteJson("/api/v1/trading/alerts/{$alert->id}", [], $this->headers);

    $response->assertNoContent();
    expect(TradeAlert::find($alert->id))->toBeNull();
});

it('requires threshold for pnl conditions', function () {
    $response = $this->postJson('/api/v1/trading/alerts', [
        'condition' => 'pnl_above',
    ], $this->headers);

    $response->assertUnprocessable();
});

it('limits alerts to 25 per agent', function () {
    TradeAlert::factory()->count(25)->create(['agent_id' => $this->agent->id]);

    $response = $this->postJson('/api/v1/trading/alerts', [
        'condition' => 'trade_opened',
    ], $this->headers);

    $response->assertStatus(422);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/TradeAlertTest.php --filter="creates a trade alert" -v`
Expected: FAIL — route not found

- [ ] **Step 3: Create TradeAlertController**

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\TradeAlert;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

class TradeAlertController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $alerts = TradeAlert::where('agent_id', $request->agent->id)
            ->orderByDesc('created_at')
            ->get();

        return response()->json(['data' => $alerts]);
    }

    public function store(Request $request): JsonResponse
    {
        $count = TradeAlert::where('agent_id', $request->agent->id)->count();
        if ($count >= 25) {
            return response()->json(['message' => 'Maximum 25 alerts per agent.'], 422);
        }

        $validated = $request->validate([
            'ticker' => 'nullable|string|max:64',
            'condition' => ['required', Rule::in(TradeAlert::CONDITIONS)],
            'threshold' => 'nullable|required_if:condition,pnl_above|required_if:condition,pnl_below|numeric',
            'delivery' => 'nullable|string|in:webhook,poll',
        ]);

        $alert = TradeAlert::create([
            'agent_id' => $request->agent->id,
            ...$validated,
        ]);

        return response()->json(['data' => $alert], 201);
    }

    public function destroy(Request $request, string $id): JsonResponse
    {
        $alert = TradeAlert::where('agent_id', $request->agent->id)->findOrFail($id);
        $alert->delete();

        return response()->json(null, 204);
    }
}
```

- [ ] **Step 4: Create TradeAlert factory**

```php
<?php

namespace Database\Factories;

use App\Models\Agent;
use App\Models\TradeAlert;
use Illuminate\Database\Eloquent\Factories\Factory;

class TradeAlertFactory extends Factory
{
    protected $model = TradeAlert::class;

    public function definition(): array
    {
        return [
            'agent_id' => Agent::factory(),
            'condition' => $this->faker->randomElement(TradeAlert::CONDITIONS),
            'is_active' => true,
        ];
    }
}
```

Add `use Illuminate\Database\Eloquent\Factories\HasFactory;` and the `HasFactory` trait to `TradeAlert` model.

- [ ] **Step 5: Add routes**

In `routes/api.php`, inside the authenticated group, add after the trading routes:

```php
// Trading alerts
Route::get('trading/alerts', [TradeAlertController::class, 'index']);
Route::post('trading/alerts', [TradeAlertController::class, 'store']);
Route::delete('trading/alerts/{id}', [TradeAlertController::class, 'destroy']);
```

Add the import at top: `use App\Http\Controllers\Api\TradeAlertController;`

- [ ] **Step 6: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradeAlertTest.php -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/Http/Controllers/Api/TradeAlertController.php database/factories/TradeAlertFactory.php routes/api.php tests/Feature/TradeAlertTest.php app/Models/TradeAlert.php
git commit -m "feat(trading): add trade alert CRUD endpoints"
```

### Task 9: Evaluate Alerts on Trade Events

**Files:**
- Create: `app/Listeners/EvaluateTradeAlerts.php`
- Modify: `app/Providers/AppServiceProvider.php`

- [ ] **Step 1: Write the failing test**

Add to `tests/Feature/TradeAlertTest.php`:

```php
use App\Events\TradeClosed;
use App\Events\TradeOpened;
use App\Jobs\DispatchWebhook;
use App\Models\Trade;
use App\Models\WebhookSubscription;
use Illuminate\Support\Facades\Queue;

it('triggers alert when trade_closed condition matches', function () {
    Queue::fake();

    // Agent subscribes to alerts AND has a webhook for alert delivery
    $alert = TradeAlert::create([
        'agent_id' => $this->agent->id,
        'condition' => 'trade_closed',
        'ticker' => 'AAPL',
        'is_active' => true,
    ]);

    WebhookSubscription::create([
        'agent_id' => $this->agent->id,
        'url' => 'https://example.com/alerts',
        'events' => ['alert.triggered'],
        'secret' => 'secret',
        'is_active' => true,
    ]);

    $trade = Trade::factory()->create([
        'agent_id' => Agent::factory()->create()->id,
        'ticker' => 'AAPL',
        'status' => 'closed',
        'paper' => false,
        'pnl' => '100.00',
    ]);

    TradeClosed::dispatch($trade);

    Queue::assertPushed(DispatchWebhook::class);
    expect($alert->fresh()->trigger_count)->toBe(1);
});

it('triggers pnl_above alert when threshold is exceeded', function () {
    Queue::fake();

    TradeAlert::create([
        'agent_id' => $this->agent->id,
        'condition' => 'pnl_above',
        'threshold' => '50.00',
        'is_active' => true,
    ]);

    WebhookSubscription::create([
        'agent_id' => $this->agent->id,
        'url' => 'https://example.com/alerts',
        'events' => ['alert.triggered'],
        'secret' => 'secret',
        'is_active' => true,
    ]);

    $trade = Trade::factory()->create([
        'status' => 'closed',
        'paper' => false,
        'pnl' => '75.00',
    ]);

    TradeClosed::dispatch($trade);

    Queue::assertPushed(DispatchWebhook::class);
});

it('does not trigger alert when ticker does not match', function () {
    Queue::fake();

    TradeAlert::create([
        'agent_id' => $this->agent->id,
        'condition' => 'trade_closed',
        'ticker' => 'TSLA',
        'is_active' => true,
    ]);

    $trade = Trade::factory()->create([
        'ticker' => 'AAPL',
        'status' => 'closed',
        'paper' => false,
    ]);

    TradeClosed::dispatch($trade);

    Queue::assertNothingPushed();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/TradeAlertTest.php --filter="triggers alert" -v`
Expected: FAIL — no listener for alert evaluation

- [ ] **Step 3: Create EvaluateTradeAlerts listener**

```php
<?php

namespace App\Listeners;

use App\Events\TradeClosed;
use App\Events\TradeOpened;
use App\Jobs\DispatchWebhook;
use App\Models\TradeAlert;
use App\Models\WebhookSubscription;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Support\Str;

class EvaluateTradeAlerts implements ShouldQueue
{
    public function handleTradeOpened(TradeOpened $event): void
    {
        if ($event->trade->paper) {
            return;
        }

        $this->evaluate('trade_opened', $event->trade);
    }

    public function handleTradeClosed(TradeClosed $event): void
    {
        if ($event->trade->paper) {
            return;
        }

        $this->evaluate('trade_closed', $event->trade);

        // Also check PnL-based alerts
        if ($event->trade->pnl !== null) {
            $pnl = (float) $event->trade->pnl;
            if ($pnl > 0) {
                $this->evaluatePnl('pnl_above', $pnl, $event->trade);
            } else {
                $this->evaluatePnl('pnl_below', $pnl, $event->trade);
            }
        }
    }

    private function evaluate(string $condition, $trade): void
    {
        $alerts = TradeAlert::where('condition', $condition)
            ->where('is_active', true)
            ->where(function ($q) use ($trade) {
                $q->whereNull('ticker')->orWhere('ticker', $trade->ticker);
            })
            ->get();

        foreach ($alerts as $alert) {
            $this->triggerAlert($alert, $trade);
        }
    }

    private function evaluatePnl(string $condition, float $pnl, $trade): void
    {
        $query = TradeAlert::where('condition', $condition)
            ->where('is_active', true)
            ->where(function ($q) use ($trade) {
                $q->whereNull('ticker')->orWhere('ticker', $trade->ticker);
            });

        if ($condition === 'pnl_above') {
            $query->where('threshold', '<=', $pnl);
        } else {
            $query->where('threshold', '>=', $pnl);
        }

        foreach ($query->get() as $alert) {
            $this->triggerAlert($alert, $trade);
        }
    }

    private function triggerAlert(TradeAlert $alert, $trade): void
    {
        $alert->increment('trigger_count');
        $alert->update(['last_triggered_at' => now()]);

        $subscriptions = WebhookSubscription::where('agent_id', $alert->agent_id)
            ->where('is_active', true)
            ->whereJsonContains('events', 'alert.triggered')
            ->get();

        foreach ($subscriptions as $sub) {
            DispatchWebhook::dispatch($sub, [
                'id' => (string) Str::uuid(),
                'event' => 'alert.triggered',
                'timestamp' => now()->toIso8601String(),
                'data' => [
                    'alert_id' => $alert->id,
                    'condition' => $alert->condition,
                    'ticker' => $trade->ticker,
                    'trade_id' => $trade->id,
                    'pnl' => $trade->pnl,
                    'direction' => $trade->direction,
                    'agent_name' => $trade->agent->name ?? null,
                ],
            ]);
        }
    }
}
```

- [ ] **Step 4: Register listeners and update webhook validation**

In `app/Providers/AppServiceProvider.php`, add:

```php
use App\Listeners\EvaluateTradeAlerts;

Event::listen(TradeOpened::class, [EvaluateTradeAlerts::class, 'handleTradeOpened']);
Event::listen(TradeClosed::class, [EvaluateTradeAlerts::class, 'handleTradeClosed']);
```

In `app/Http/Controllers/Api/WebhookController.php`, add `'alert.triggered'` to the valid events list:

```php
'events.*' => 'required|string|in:memory.shared,memory.semantic_match,trade.opened,trade.closed,position.changed,alert.triggered',
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradeAlertTest.php -v`
Expected: All 9 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/Listeners/EvaluateTradeAlerts.php app/Providers/AppServiceProvider.php app/Http/Controllers/Api/WebhookController.php tests/Feature/TradeAlertTest.php
git commit -m "feat(trading): evaluate trade alerts on trade events and dispatch webhooks"
```

---

## Phase 4: Copy-Trading Signals Feed

### Task 10: Add Signal Broadcasting Flag to Agents

**Files:**
- Create: `database/migrations/2026_04_01_000003_add_signal_broadcasting_to_agents_table.php`

- [ ] **Step 1: Create migration**

Run: `php artisan make:migration add_signal_broadcasting_to_agents_table --table=agents`

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('agents', function (Blueprint $table) {
            $table->boolean('broadcasts_signals')->default(false)->after('is_listed');
        });
    }

    public function down(): void
    {
        Schema::table('agents', function (Blueprint $table) {
            $table->dropColumn('broadcasts_signals');
        });
    }
};
```

- [ ] **Step 2: Update Agent model**

In `app/Models/Agent.php`, add `'broadcasts_signals'` to `$fillable` and to `$casts`:

```php
'broadcasts_signals' => 'boolean',
```

- [ ] **Step 3: Run migration**

Run: `php artisan migrate`

- [ ] **Step 4: Commit**

```bash
git add database/migrations/*add_signal_broadcasting_to_agents_table.php app/Models/Agent.php
git commit -m "feat(trading): add broadcasts_signals flag to agents"
```

### Task 11: Signal Feed Controller

**Files:**
- Create: `app/Http/Controllers/Api/SignalController.php`
- Modify: `routes/api.php`
- Create: `tests/Feature/SignalFeedTest.php`

- [ ] **Step 1: Write the failing test**

Create `tests/Feature/SignalFeedTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\Trade;

beforeEach(function () {
    $this->agent = Agent::factory()->create();
    $this->headers = ['Authorization' => "Bearer {$this->agent->api_token}"];
});

it('lists recent signals from broadcasting agents', function () {
    $broadcaster = Agent::factory()->create([
        'is_listed' => true,
        'broadcasts_signals' => true,
    ]);

    // Create a closed live trade for the broadcaster
    $parent = Trade::factory()->create([
        'agent_id' => $broadcaster->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '150.00',
        'quantity' => '10',
        'status' => 'closed',
        'exit_price' => '160.00',
        'pnl' => '100.00',
        'paper' => false,
        'exit_at' => now(),
    ]);

    $response = $this->getJson('/api/v1/trading/signals', $this->headers);

    $response->assertOk();
    expect($response->json('data'))->toHaveCount(1);
    expect($response->json('data.0.ticker'))->toBe('AAPL');
    expect($response->json('data.0.agent_name'))->toBe($broadcaster->name);
});

it('excludes paper trades from signal feed', function () {
    $broadcaster = Agent::factory()->create([
        'is_listed' => true,
        'broadcasts_signals' => true,
    ]);

    Trade::factory()->create([
        'agent_id' => $broadcaster->id,
        'paper' => true,
        'status' => 'closed',
    ]);

    $response = $this->getJson('/api/v1/trading/signals', $this->headers);

    $response->assertOk();
    expect($response->json('data'))->toHaveCount(0);
});

it('excludes non-broadcasting agents', function () {
    $nonBroadcaster = Agent::factory()->create([
        'is_listed' => true,
        'broadcasts_signals' => false,
    ]);

    Trade::factory()->create([
        'agent_id' => $nonBroadcaster->id,
        'paper' => false,
        'status' => 'closed',
    ]);

    $response = $this->getJson('/api/v1/trading/signals', $this->headers);

    $response->assertOk();
    expect($response->json('data'))->toHaveCount(0);
});

it('allows filtering signals by ticker', function () {
    $broadcaster = Agent::factory()->create([
        'is_listed' => true,
        'broadcasts_signals' => true,
    ]);

    Trade::factory()->create([
        'agent_id' => $broadcaster->id,
        'ticker' => 'AAPL',
        'paper' => false,
        'status' => 'open',
    ]);
    Trade::factory()->create([
        'agent_id' => $broadcaster->id,
        'ticker' => 'TSLA',
        'paper' => false,
        'status' => 'open',
    ]);

    $response = $this->getJson('/api/v1/trading/signals?ticker=AAPL', $this->headers);

    $response->assertOk();
    expect($response->json('data'))->toHaveCount(1);
});

it('allows agent to enable signal broadcasting', function () {
    $response = $this->patchJson('/api/v1/agents/me', [
        'broadcasts_signals' => true,
    ], $this->headers);

    $response->assertOk();
    expect($this->agent->fresh()->broadcasts_signals)->toBeTrue();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/SignalFeedTest.php --filter="lists recent signals" -v`
Expected: FAIL — route not found

- [ ] **Step 3: Create SignalController**

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\Trade;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class SignalController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $broadcasterIds = Agent::where('broadcasts_signals', true)
            ->where('is_listed', true)
            ->pluck('id');

        $query = Trade::whereIn('agent_id', $broadcasterIds)
            ->where('paper', false)
            ->whereNull('parent_trade_id')
            ->with('agent:id,name')
            ->orderByDesc('created_at');

        if ($request->has('ticker')) {
            $query->where('ticker', $request->input('ticker'));
        }

        if ($request->has('direction')) {
            $query->where('direction', $request->input('direction'));
        }

        if ($request->has('status')) {
            $query->where('status', $request->input('status'));
        }

        $trades = $query->cursorPaginate($request->input('limit', 50));

        $data = collect($trades->items())->map(fn (Trade $t) => [
            'trade_id' => $t->id,
            'agent_id' => $t->agent_id,
            'agent_name' => $t->agent?->name,
            'ticker' => $t->ticker,
            'direction' => $t->direction,
            'entry_price' => $t->entry_price,
            'exit_price' => $t->exit_price,
            'quantity' => $t->quantity,
            'pnl' => $t->pnl,
            'pnl_percent' => $t->pnl_percent,
            'status' => $t->status,
            'strategy' => $t->strategy,
            'tags' => $t->tags,
            'entry_at' => $t->entry_at?->toIso8601String(),
            'exit_at' => $t->exit_at?->toIso8601String(),
            'created_at' => $t->created_at->toIso8601String(),
        ]);

        return response()->json([
            'data' => $data,
            'next_cursor' => $trades->nextCursor()?->encode(),
        ]);
    }
}
```

- [ ] **Step 4: Add routes**

In `routes/api.php`, inside the authenticated group:

```php
// Signals feed
Route::get('trading/signals', [SignalController::class, 'index']);
```

Add import: `use App\Http\Controllers\Api\SignalController;`

- [ ] **Step 5: Ensure AgentController accepts broadcasts_signals in update**

In `app/Http/Controllers/Api/AgentController.php`, in the `update` method's validation rules, add:

```php
'broadcasts_signals' => 'nullable|boolean',
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `php artisan test tests/Feature/SignalFeedTest.php -v`
Expected: All 5 tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/Http/Controllers/Api/SignalController.php app/Http/Controllers/Api/AgentController.php routes/api.php tests/Feature/SignalFeedTest.php
git commit -m "feat(trading): add copy-trading signal feed endpoint"
```

---

## Phase 5: Risk Metrics on Positions

### Task 12: Add Risk Fields to Positions

**Files:**
- Create: `database/migrations/2026_04_01_000004_add_risk_fields_to_positions_table.php`
- Create: `app/Services/RiskService.php`
- Create: `app/Http/Controllers/Api/RiskController.php`

- [ ] **Step 1: Create migration**

Run: `php artisan make:migration add_risk_fields_to_positions_table --table=positions`

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('positions', function (Blueprint $table) {
            $table->decimal('declared_portfolio_value', 24, 8)->nullable()->after('avg_entry_price');
            $table->decimal('max_drawdown', 24, 8)->nullable()->after('declared_portfolio_value');
        });
    }

    public function down(): void
    {
        Schema::table('positions', function (Blueprint $table) {
            $table->dropColumn(['declared_portfolio_value', 'max_drawdown']);
        });
    }
};
```

- [ ] **Step 2: Run migration**

Run: `php artisan migrate`

- [ ] **Step 3: Update Position model**

Add `'declared_portfolio_value'` and `'max_drawdown'` to `$fillable` and `$casts`:

```php
'declared_portfolio_value' => 'decimal:8',
'max_drawdown' => 'decimal:8',
```

- [ ] **Step 4: Commit**

```bash
git add database/migrations/*add_risk_fields_to_positions_table.php app/Models/Position.php
git commit -m "feat(trading): add risk fields to positions table"
```

### Task 13: Risk Service and Controller

**Files:**
- Create: `app/Services/RiskService.php`
- Create: `app/Http/Controllers/Api/RiskController.php`
- Create: `tests/Feature/RiskMetricsTest.php`

- [ ] **Step 1: Write the failing test**

Create `tests/Feature/RiskMetricsTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\Position;
use App\Models\Trade;

beforeEach(function () {
    $this->agent = Agent::factory()->create();
    $this->headers = ['Authorization' => "Bearer {$this->agent->api_token}"];
});

it('returns risk metrics for open positions', function () {
    Position::create([
        'agent_id' => $this->agent->id,
        'ticker' => 'AAPL',
        'paper' => false,
        'quantity' => '10.00000000',
        'avg_entry_price' => '150.00000000',
    ]);

    $response = $this->getJson('/api/v1/trading/risk?market_prices[AAPL]=160.00', $this->headers);

    $response->assertOk();
    $data = $response->json('data');
    expect($data)->toHaveCount(1);
    expect($data[0]['ticker'])->toBe('AAPL');
    expect((float) $data[0]['unrealized_pnl'])->toBe(100.0); // (160-150)*10
    expect((float) $data[0]['exposure'])->toBe(1600.0);       // 160*10
});

it('calculates exposure percentage when portfolio value is declared', function () {
    Position::create([
        'agent_id' => $this->agent->id,
        'ticker' => 'AAPL',
        'paper' => false,
        'quantity' => '10.00000000',
        'avg_entry_price' => '150.00000000',
        'declared_portfolio_value' => '10000.00000000',
    ]);

    $response = $this->getJson('/api/v1/trading/risk?market_prices[AAPL]=150.00', $this->headers);

    $response->assertOk();
    expect((float) $response->json('data.0.exposure_pct'))->toBe(15.0); // 1500/10000*100
});

it('returns max drawdown from closed trades', function () {
    // Create some closed trades with varying PnL
    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'AAPL',
        'status' => 'closed',
        'paper' => false,
        'pnl' => '50.00',
        'exit_at' => now()->subDays(3),
    ]);
    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'AAPL',
        'status' => 'closed',
        'paper' => false,
        'pnl' => '-30.00',
        'exit_at' => now()->subDays(2),
    ]);
    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'AAPL',
        'status' => 'closed',
        'paper' => false,
        'pnl' => '-20.00',
        'exit_at' => now()->subDay(),
    ]);

    $response = $this->getJson('/api/v1/trading/risk/drawdown?paper=false', $this->headers);

    $response->assertOk();
    // Peak was 50, trough is 50-30-20=0, so drawdown is -50
    expect((float) $response->json('data.max_drawdown'))->toBe(-50.0);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/RiskMetricsTest.php --filter="returns risk metrics" -v`
Expected: FAIL — route not found

- [ ] **Step 3: Create RiskService**

```php
<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Position;
use App\Models\Trade;

class RiskService
{
    public function calculatePositionRisk(Position $position, ?string $marketPrice): array
    {
        $qty = (float) $position->quantity;
        $avgEntry = (float) $position->avg_entry_price;
        $price = $marketPrice !== null ? (float) $marketPrice : $avgEntry;
        $exposure = $price * $qty;
        $unrealizedPnl = ($price - $avgEntry) * $qty;
        $portfolioValue = $position->declared_portfolio_value ? (float) $position->declared_portfolio_value : null;
        $exposurePct = $portfolioValue ? ($exposure / $portfolioValue) * 100 : null;

        return [
            'ticker' => $position->ticker,
            'paper' => $position->paper,
            'quantity' => $position->quantity,
            'avg_entry_price' => $position->avg_entry_price,
            'market_price' => $marketPrice ?? $position->avg_entry_price,
            'unrealized_pnl' => round($unrealizedPnl, 8),
            'exposure' => round($exposure, 8),
            'exposure_pct' => $exposurePct !== null ? round($exposurePct, 2) : null,
        ];
    }

    public function calculateMaxDrawdown(Agent $agent, bool $paper): array
    {
        $trades = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->whereNotNull('pnl')
            ->orderBy('exit_at')
            ->pluck('pnl')
            ->map(fn ($v) => (float) $v);

        if ($trades->isEmpty()) {
            return ['max_drawdown' => 0, 'peak' => 0, 'trough' => 0];
        }

        $cumulative = 0;
        $peak = 0;
        $maxDrawdown = 0;
        $trough = 0;

        foreach ($trades as $pnl) {
            $cumulative += $pnl;
            if ($cumulative > $peak) {
                $peak = $cumulative;
            }
            $drawdown = $cumulative - $peak;
            if ($drawdown < $maxDrawdown) {
                $maxDrawdown = $drawdown;
                $trough = $cumulative;
            }
        }

        return [
            'max_drawdown' => round($maxDrawdown, 8),
            'peak' => round($peak, 8),
            'trough' => round($trough, 8),
        ];
    }
}
```

- [ ] **Step 4: Create RiskController**

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Position;
use App\Services\RiskService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class RiskController extends Controller
{
    public function __construct(
        private RiskService $riskService,
    ) {}

    public function index(Request $request): JsonResponse
    {
        $request->validate([
            'market_prices' => 'nullable|array',
            'market_prices.*' => 'numeric',
            'paper' => 'nullable|boolean',
        ]);

        $paper = filter_var($request->input('paper', false), FILTER_VALIDATE_BOOLEAN);
        $marketPrices = $request->input('market_prices', []);

        $positions = Position::where('agent_id', $request->agent->id)
            ->where('paper', $paper)
            ->get();

        $data = $positions->map(fn (Position $p) => $this->riskService->calculatePositionRisk(
            $p,
            $marketPrices[$p->ticker] ?? null,
        ));

        return response()->json(['data' => $data]);
    }

    public function drawdown(Request $request): JsonResponse
    {
        $paper = filter_var($request->input('paper', false), FILTER_VALIDATE_BOOLEAN);

        $result = $this->riskService->calculateMaxDrawdown($request->agent, $paper);

        return response()->json(['data' => $result]);
    }
}
```

- [ ] **Step 5: Add routes**

In `routes/api.php`, inside the authenticated group:

```php
// Risk metrics
Route::get('trading/risk', [RiskController::class, 'index']);
Route::get('trading/risk/drawdown', [RiskController::class, 'drawdown']);
```

Add import: `use App\Http\Controllers\Api\RiskController;`

- [ ] **Step 6: Run tests to verify they pass**

Run: `php artisan test tests/Feature/RiskMetricsTest.php -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/Services/RiskService.php app/Http/Controllers/Api/RiskController.php routes/api.php tests/Feature/RiskMetricsTest.php
git commit -m "feat(trading): add risk metrics and drawdown endpoints"
```

---

## Phase 6: Correlation Endpoint

### Task 14: Add Correlations Method to TradingStatsController

**Files:**
- Modify: `app/Http/Controllers/Api/TradingStatsController.php`
- Modify: `routes/api.php`
- Create: `tests/Feature/TradeCorrelationTest.php`

- [ ] **Step 1: Write the failing test**

Create `tests/Feature/TradeCorrelationTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\Trade;

beforeEach(function () {
    $this->agent = Agent::factory()->create();
    $this->headers = ['Authorization' => "Bearer {$this->agent->api_token}"];
});

it('returns correlation matrix between tickers', function () {
    // Create closed trades for AAPL and TSLA with PnL values
    foreach (range(1, 10) as $i) {
        Trade::factory()->create([
            'agent_id' => $this->agent->id,
            'ticker' => 'AAPL',
            'status' => 'closed',
            'paper' => false,
            'pnl' => $i * 10,
            'exit_at' => now()->subDays(10 - $i),
        ]);
        Trade::factory()->create([
            'agent_id' => $this->agent->id,
            'ticker' => 'TSLA',
            'status' => 'closed',
            'paper' => false,
            'pnl' => $i * 5,
            'exit_at' => now()->subDays(10 - $i),
        ]);
    }

    $response = $this->getJson('/api/v1/trading/stats/correlations?paper=false', $this->headers);

    $response->assertOk();
    $data = $response->json('data');
    expect($data)->toHaveKey('AAPL');
    expect($data['AAPL'])->toHaveKey('TSLA');
    // Perfectly correlated PnL series
    expect((float) $data['AAPL']['TSLA'])->toBeGreaterThan(0.9);
});

it('returns empty data with insufficient trades', function () {
    $response = $this->getJson('/api/v1/trading/stats/correlations?paper=false', $this->headers);

    $response->assertOk();
    expect($response->json('data'))->toBeEmpty();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/TradeCorrelationTest.php --filter="returns correlation matrix" -v`
Expected: FAIL — route not found

- [ ] **Step 3: Add correlations method to TradingStatsController**

In `app/Http/Controllers/Api/TradingStatsController.php`, add:

```php
public function correlations(Request $request): JsonResponse
{
    $paper = filter_var($request->input('paper', false), FILTER_VALIDATE_BOOLEAN);

    $trades = Trade::where('agent_id', $request->agent->id)
        ->where('paper', $paper)
        ->where('status', 'closed')
        ->whereNull('parent_trade_id')
        ->whereNotNull('pnl')
        ->orderBy('exit_at')
        ->get(['ticker', 'pnl', 'exit_at']);

    // Group PnL series by ticker
    $series = [];
    foreach ($trades as $trade) {
        $series[$trade->ticker][] = (float) $trade->pnl;
    }

    // Need at least 2 tickers with 3+ trades each
    $series = array_filter($series, fn ($s) => count($s) >= 3);
    $tickers = array_keys($series);

    if (count($tickers) < 2) {
        return response()->json(['data' => (object) []]);
    }

    // Compute Pearson correlation for each pair
    $matrix = [];
    foreach ($tickers as $a) {
        $matrix[$a] = [];
        foreach ($tickers as $b) {
            if ($a === $b) {
                $matrix[$a][$b] = 1.0;
                continue;
            }
            $matrix[$a][$b] = $this->pearson($series[$a], $series[$b]);
        }
    }

    return response()->json(['data' => $matrix]);
}

private function pearson(array $x, array $y): ?float
{
    $n = min(count($x), count($y));
    if ($n < 3) {
        return null;
    }

    $x = array_slice($x, 0, $n);
    $y = array_slice($y, 0, $n);

    $meanX = array_sum($x) / $n;
    $meanY = array_sum($y) / $n;

    $num = 0;
    $denomX = 0;
    $denomY = 0;

    for ($i = 0; $i < $n; $i++) {
        $dx = $x[$i] - $meanX;
        $dy = $y[$i] - $meanY;
        $num += $dx * $dy;
        $denomX += $dx * $dx;
        $denomY += $dy * $dy;
    }

    $denom = sqrt($denomX * $denomY);

    return $denom > 0 ? round($num / $denom, 4) : null;
}
```

- [ ] **Step 4: Add route**

In `routes/api.php`, inside the authenticated group, add before the `trading/stats` line (so the specific route matches first):

```php
Route::get('trading/stats/correlations', [TradingStatsController::class, 'correlations']);
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradeCorrelationTest.php -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/Http/Controllers/Api/TradingStatsController.php routes/api.php tests/Feature/TradeCorrelationTest.php
git commit -m "feat(trading): add ticker-pair PnL correlation endpoint"
```

---

## Phase 7: Export Endpoints

### Task 15: Trade Export Controller

**Files:**
- Create: `app/Http/Controllers/Api/TradeExportController.php`
- Modify: `routes/api.php`
- Create: `tests/Feature/TradeExportTest.php`

- [ ] **Step 1: Write the failing test**

Create `tests/Feature/TradeExportTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\Trade;

beforeEach(function () {
    $this->agent = Agent::factory()->create();
    $this->headers = ['Authorization' => "Bearer {$this->agent->api_token}"];
});

it('exports trades as JSON', function () {
    Trade::factory()->count(3)->create([
        'agent_id' => $this->agent->id,
        'paper' => false,
        'status' => 'closed',
    ]);

    $response = $this->getJson('/api/v1/trading/export?format=json&paper=false', $this->headers);

    $response->assertOk();
    expect($response->json('data'))->toHaveCount(3);
    expect($response->json('data.0'))->toHaveKeys([
        'id', 'ticker', 'direction', 'entry_price', 'exit_price',
        'quantity', 'fees', 'pnl', 'pnl_percent', 'strategy', 'tags',
        'entry_at', 'exit_at', 'status',
    ]);
});

it('exports trades as CSV', function () {
    Trade::factory()->count(2)->create([
        'agent_id' => $this->agent->id,
        'paper' => false,
        'status' => 'closed',
    ]);

    $response = $this->get('/api/v1/trading/export?format=csv&paper=false', $this->headers);

    $response->assertOk();
    $response->assertHeader('content-type', 'text/csv; charset=UTF-8');
    $response->assertHeader('content-disposition');

    $lines = explode("\n", trim($response->getContent()));
    expect($lines)->toHaveCount(3); // header + 2 rows
});

it('filters export by date range', function () {
    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'paper' => false,
        'entry_at' => now()->subDays(10),
    ]);
    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'paper' => false,
        'entry_at' => now()->subDays(2),
    ]);

    $from = now()->subDays(5)->toDateString();
    $response = $this->getJson("/api/v1/trading/export?format=json&paper=false&from={$from}", $this->headers);

    $response->assertOk();
    expect($response->json('data'))->toHaveCount(1);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/TradeExportTest.php --filter="exports trades as JSON" -v`
Expected: FAIL — route not found

- [ ] **Step 3: Create TradeExportController**

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Trade;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\StreamedResponse;

class TradeExportController extends Controller
{
    public function export(Request $request): JsonResponse|StreamedResponse
    {
        $request->validate([
            'format' => 'nullable|string|in:json,csv',
            'paper' => 'nullable',
            'from' => 'nullable|date',
            'to' => 'nullable|date',
            'status' => 'nullable|string|in:open,closed,cancelled',
            'ticker' => 'nullable|string|max:64',
        ]);

        $paper = filter_var($request->input('paper', false), FILTER_VALIDATE_BOOLEAN);
        $format = $request->input('format', 'json');

        $query = Trade::where('agent_id', $request->agent->id)
            ->where('paper', $paper)
            ->whereNull('parent_trade_id')
            ->orderBy('entry_at');

        if ($request->has('from')) {
            $query->where('entry_at', '>=', $request->input('from'));
        }
        if ($request->has('to')) {
            $query->where('entry_at', '<=', $request->input('to'));
        }
        if ($request->has('status')) {
            $query->where('status', $request->input('status'));
        }
        if ($request->has('ticker')) {
            $query->where('ticker', $request->input('ticker'));
        }

        $columns = [
            'id', 'ticker', 'direction', 'entry_price', 'exit_price',
            'quantity', 'fees', 'pnl', 'pnl_percent', 'strategy', 'tags',
            'entry_at', 'exit_at', 'status', 'confidence', 'paper',
        ];

        if ($format === 'csv') {
            return $this->streamCsv($query, $columns);
        }

        $trades = $query->get($columns)->map(function ($t) {
            $row = $t->toArray();
            $row['entry_at'] = $t->entry_at?->toIso8601String();
            $row['exit_at'] = $t->exit_at?->toIso8601String();

            return $row;
        });

        return response()->json(['data' => $trades]);
    }

    private function streamCsv($query, array $columns): StreamedResponse
    {
        $headers = [
            'Content-Type' => 'text/csv; charset=UTF-8',
            'Content-Disposition' => 'attachment; filename="trades-export-'.now()->format('Y-m-d').'.csv"',
        ];

        return response()->stream(function () use ($query, $columns) {
            $handle = fopen('php://output', 'w');
            fputcsv($handle, $columns);

            $query->chunk(500, function ($trades) use ($handle, $columns) {
                foreach ($trades as $trade) {
                    $row = [];
                    foreach ($columns as $col) {
                        $val = $trade->{$col};
                        if ($val instanceof \DateTimeInterface) {
                            $val = $val->toIso8601String();
                        } elseif (is_array($val)) {
                            $val = implode(';', $val);
                        }
                        $row[] = $val;
                    }
                    fputcsv($handle, $row);
                }
            });

            fclose($handle);
        }, 200, $headers);
    }
}
```

- [ ] **Step 4: Add route**

In `routes/api.php`, inside the authenticated group:

```php
// Export
Route::get('trading/export', [TradeExportController::class, 'export']);
```

Add import: `use App\Http\Controllers\Api\TradeExportController;`

- [ ] **Step 5: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradeExportTest.php -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/Http/Controllers/Api/TradeExportController.php routes/api.php tests/Feature/TradeExportTest.php
git commit -m "feat(trading): add JSON and CSV trade export endpoints"
```

---

## Phase 8: Trade Replay/Simulation

### Task 16: Replay Service and Controller

**Files:**
- Create: `app/Services/ReplayService.php`
- Create: `app/Http/Controllers/Api/ReplayController.php`
- Modify: `routes/api.php`
- Create: `tests/Feature/TradeReplayTest.php`

- [ ] **Step 1: Write the failing test**

Create `tests/Feature/TradeReplayTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\Trade;

beforeEach(function () {
    $this->agent = Agent::factory()->create();
    $this->headers = ['Authorization' => "Bearer {$this->agent->api_token}"];
});

it('replays historical trades with original exit prices', function () {
    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '100.00',
        'exit_price' => '110.00',
        'quantity' => '10',
        'fees' => '5.00',
        'status' => 'closed',
        'pnl' => '95.00',
        'paper' => false,
    ]);
    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'TSLA',
        'direction' => 'short',
        'entry_price' => '200.00',
        'exit_price' => '190.00',
        'quantity' => '5',
        'fees' => '3.00',
        'status' => 'closed',
        'pnl' => '47.00',
        'paper' => false,
    ]);

    $response = $this->postJson('/api/v1/trading/replay', [
        'paper' => false,
    ], $this->headers);

    $response->assertOk();
    $data = $response->json('data');
    expect($data['total_trades'])->toBe(2);
    expect((float) $data['total_pnl'])->toBe(142.0);
    expect((float) $data['win_rate'])->toBe(100.0);
});

it('replays with alternative exit prices', function () {
    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '100.00',
        'exit_price' => '110.00',
        'quantity' => '10',
        'fees' => '0',
        'status' => 'closed',
        'pnl' => '100.00',
        'paper' => false,
    ]);

    $response = $this->postJson('/api/v1/trading/replay', [
        'paper' => false,
        'exit_overrides' => [
            'AAPL' => '90.00',  // What if AAPL dropped instead?
        ],
    ], $this->headers);

    $response->assertOk();
    $data = $response->json('data');
    // Long trade: (90-100)*10 = -100
    expect((float) $data['total_pnl'])->toBe(-100.0);
    expect((float) $data['win_rate'])->toBe(0.0);
});

it('replays with exit_offset percentage', function () {
    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '100.00',
        'exit_price' => '110.00',
        'quantity' => '10',
        'fees' => '0',
        'status' => 'closed',
        'paper' => false,
    ]);

    // What if we exited 5% earlier (at 105% of entry instead of 110%)?
    $response = $this->postJson('/api/v1/trading/replay', [
        'paper' => false,
        'exit_offset_pct' => -5.0,  // shift all exits 5% lower
    ], $this->headers);

    $response->assertOk();
    // Original exit 110, offset by -5% = 110 * 0.95 = 104.5
    // PnL: (104.5 - 100) * 10 = 45
    expect((float) $response->json('data.total_pnl'))->toBe(45.0);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/TradeReplayTest.php --filter="replays historical" -v`
Expected: FAIL — route not found

- [ ] **Step 3: Create ReplayService**

```php
<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Trade;

class ReplayService
{
    public function replay(Agent $agent, bool $paper, array $exitOverrides = [], ?float $exitOffsetPct = null): array
    {
        $trades = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->orderBy('exit_at')
            ->get();

        $results = [];
        $totalPnl = 0;
        $wins = 0;
        $losses = 0;
        $cumulative = [];

        foreach ($trades as $trade) {
            $entryPrice = (float) $trade->entry_price;
            $quantity = (float) $trade->quantity;
            $fees = (float) $trade->fees;

            // Determine exit price: override > offset > original
            if (isset($exitOverrides[$trade->ticker])) {
                $exitPrice = (float) $exitOverrides[$trade->ticker];
            } elseif ($exitOffsetPct !== null && $trade->exit_price !== null) {
                $exitPrice = (float) $trade->exit_price * (1 + $exitOffsetPct / 100);
            } else {
                $exitPrice = (float) $trade->exit_price;
            }

            // Compute PnL
            if ($trade->direction === 'long') {
                $pnl = ($exitPrice - $entryPrice) * $quantity - $fees;
            } else {
                $pnl = ($entryPrice - $exitPrice) * $quantity - $fees;
            }

            $totalPnl += $pnl;
            $pnl > 0 ? $wins++ : $losses++;

            $cumulative[] = [
                'trade_id' => $trade->id,
                'ticker' => $trade->ticker,
                'original_pnl' => (float) $trade->pnl,
                'simulated_pnl' => round($pnl, 8),
                'exit_price_used' => round($exitPrice, 8),
                'cumulative_pnl' => round($totalPnl, 8),
            ];
        }

        $total = $wins + $losses;

        return [
            'total_trades' => $total,
            'wins' => $wins,
            'losses' => $losses,
            'win_rate' => $total > 0 ? round(($wins / $total) * 100, 2) : 0,
            'total_pnl' => round($totalPnl, 8),
            'trades' => $cumulative,
        ];
    }
}
```

- [ ] **Step 4: Create ReplayController**

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Services\ReplayService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ReplayController extends Controller
{
    public function __construct(
        private ReplayService $replayService,
    ) {}

    public function replay(Request $request): JsonResponse
    {
        $request->validate([
            'paper' => 'nullable',
            'exit_overrides' => 'nullable|array',
            'exit_overrides.*' => 'numeric',
            'exit_offset_pct' => 'nullable|numeric|between:-100,1000',
        ]);

        $paper = filter_var($request->input('paper', false), FILTER_VALIDATE_BOOLEAN);

        $result = $this->replayService->replay(
            $request->agent,
            $paper,
            $request->input('exit_overrides', []),
            $request->input('exit_offset_pct'),
        );

        return response()->json(['data' => $result]);
    }
}
```

- [ ] **Step 5: Add route**

In `routes/api.php`, inside the authenticated group:

```php
// Replay / simulation
Route::post('trading/replay', [ReplayController::class, 'replay']);
```

Add import: `use App\Http\Controllers\Api\ReplayController;`

- [ ] **Step 6: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradeReplayTest.php -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/Services/ReplayService.php app/Http/Controllers/Api/ReplayController.php routes/api.php tests/Feature/TradeReplayTest.php
git commit -m "feat(trading): add trade replay/simulation endpoint with exit overrides"
```

---

## Phase 9: Multi-Agent Portfolio View

### Task 17: Portfolio Controller

**Files:**
- Create: `app/Http/Controllers/Api/PortfolioController.php`
- Modify: `routes/api.php`
- Create: `tests/Feature/MultiAgentPortfolioTest.php`

- [ ] **Step 1: Write the failing test**

Create `tests/Feature/MultiAgentPortfolioTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\Position;
use App\Models\TradingStats;
use App\Models\User;

beforeEach(function () {
    $this->owner = User::factory()->create(['api_token' => 'owner_token_123']);
    $this->agent1 = Agent::factory()->create(['owner_id' => $this->owner->id]);
    $this->agent2 = Agent::factory()->create(['owner_id' => $this->owner->id]);
    $this->headers = ['Authorization' => "Bearer {$this->agent1->api_token}"];
});

it('aggregates positions across agents owned by the same user', function () {
    Position::create([
        'agent_id' => $this->agent1->id,
        'ticker' => 'AAPL',
        'paper' => false,
        'quantity' => '10.00000000',
        'avg_entry_price' => '150.00000000',
    ]);
    Position::create([
        'agent_id' => $this->agent2->id,
        'ticker' => 'AAPL',
        'paper' => false,
        'quantity' => '5.00000000',
        'avg_entry_price' => '160.00000000',
    ]);
    Position::create([
        'agent_id' => $this->agent2->id,
        'ticker' => 'TSLA',
        'paper' => false,
        'quantity' => '20.00000000',
        'avg_entry_price' => '200.00000000',
    ]);

    $response = $this->getJson('/api/v1/trading/portfolio?paper=false', $this->headers);

    $response->assertOk();
    $data = $response->json('data.positions');
    expect($data)->toHaveCount(2); // AAPL (combined) + TSLA

    $aapl = collect($data)->firstWhere('ticker', 'AAPL');
    expect((float) $aapl['total_quantity'])->toBe(15.0);
});

it('aggregates stats across agents owned by the same user', function () {
    TradingStats::create([
        'agent_id' => $this->agent1->id,
        'paper' => false,
        'total_trades' => 10,
        'win_count' => 7,
        'loss_count' => 3,
        'total_pnl' => '500.00',
    ]);
    TradingStats::create([
        'agent_id' => $this->agent2->id,
        'paper' => false,
        'total_trades' => 5,
        'win_count' => 3,
        'loss_count' => 2,
        'total_pnl' => '200.00',
    ]);

    $response = $this->getJson('/api/v1/trading/portfolio?paper=false', $this->headers);

    $response->assertOk();
    $stats = $response->json('data.aggregate_stats');
    expect($stats['total_trades'])->toBe(15);
    expect($stats['win_count'])->toBe(10);
    expect((float) $stats['total_pnl'])->toBe(700.0);
});

it('does not include agents from other owners', function () {
    $otherAgent = Agent::factory()->create(); // different owner

    Position::create([
        'agent_id' => $otherAgent->id,
        'ticker' => 'GOOG',
        'paper' => false,
        'quantity' => '100.00000000',
        'avg_entry_price' => '300.00000000',
    ]);

    $response = $this->getJson('/api/v1/trading/portfolio?paper=false', $this->headers);

    $response->assertOk();
    $tickers = collect($response->json('data.positions'))->pluck('ticker')->toArray();
    expect($tickers)->not->toContain('GOOG');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/MultiAgentPortfolioTest.php --filter="aggregates positions" -v`
Expected: FAIL — route not found

- [ ] **Step 3: Create PortfolioController**

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\Position;
use App\Models\TradingStats;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class PortfolioController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $paper = filter_var($request->input('paper', false), FILTER_VALIDATE_BOOLEAN);
        $ownerId = $request->agent->owner_id;

        $agentIds = Agent::where('owner_id', $ownerId)->pluck('id');

        // Aggregate positions by ticker
        $positions = Position::whereIn('agent_id', $agentIds)
            ->where('paper', $paper)
            ->get()
            ->groupBy('ticker')
            ->map(function ($group, $ticker) {
                $totalQty = $group->sum(fn ($p) => (float) $p->quantity);
                $weightedPrice = $group->sum(fn ($p) => (float) $p->quantity * (float) $p->avg_entry_price);

                return [
                    'ticker' => $ticker,
                    'total_quantity' => round($totalQty, 8),
                    'avg_entry_price' => $totalQty > 0 ? round($weightedPrice / $totalQty, 8) : 0,
                    'agent_count' => $group->count(),
                ];
            })
            ->values();

        // Aggregate stats
        $stats = TradingStats::whereIn('agent_id', $agentIds)
            ->where('paper', $paper)
            ->get();

        $aggregateStats = [
            'total_trades' => $stats->sum('total_trades'),
            'win_count' => $stats->sum('win_count'),
            'loss_count' => $stats->sum('loss_count'),
            'total_pnl' => round($stats->sum(fn ($s) => (float) $s->total_pnl), 8),
            'agent_count' => $agentIds->count(),
        ];

        // Per-agent breakdown
        $agentBreakdown = Agent::whereIn('id', $agentIds)
            ->with(['tradingStats' => fn ($q) => $q->where('paper', $paper)])
            ->get()
            ->map(fn ($a) => [
                'agent_id' => $a->id,
                'agent_name' => $a->name,
                'total_pnl' => (float) ($a->tradingStats->first()?->total_pnl ?? 0),
                'total_trades' => $a->tradingStats->first()?->total_trades ?? 0,
                'win_rate' => (float) ($a->tradingStats->first()?->win_rate ?? 0),
            ]);

        return response()->json([
            'data' => [
                'positions' => $positions,
                'aggregate_stats' => $aggregateStats,
                'agents' => $agentBreakdown,
            ],
        ]);
    }
}
```

- [ ] **Step 4: Add route**

In `routes/api.php`, inside the authenticated group:

```php
// Multi-agent portfolio
Route::get('trading/portfolio', [PortfolioController::class, 'index']);
```

Add import: `use App\Http\Controllers\Api\PortfolioController;`

- [ ] **Step 5: Run tests to verify they pass**

Run: `php artisan test tests/Feature/MultiAgentPortfolioTest.php -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Run full trading test suite for regression**

Run: `php artisan test tests/Feature/Trading* tests/Feature/Trade* tests/Feature/Signal* tests/Feature/Risk* tests/Feature/MultiAgent* -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/Http/Controllers/Api/PortfolioController.php routes/api.php tests/Feature/MultiAgentPortfolioTest.php
git commit -m "feat(trading): add multi-agent portfolio aggregation endpoint"
```

---

## Phase 10: Python SDK Updates

### Task 18: Add New Dataclasses

**Files:**
- Modify: `sdk-python/remembr/models.py`

- [ ] **Step 1: Add new dataclasses to models.py**

Append to `sdk-python/remembr/models.py`:

```python
@dataclass
class RiskMetrics:
    ticker: str
    paper: bool
    quantity: str
    avg_entry_price: str
    market_price: str
    unrealized_pnl: float
    exposure: float
    exposure_pct: Optional[float] = None


@dataclass
class DrawdownResult:
    max_drawdown: float
    peak: float
    trough: float


@dataclass
class ReplayResult:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    trades: list


@dataclass
class SignalEntry:
    trade_id: str
    agent_id: str
    agent_name: Optional[str]
    ticker: str
    direction: str
    entry_price: str
    exit_price: Optional[str]
    quantity: str
    pnl: Optional[str]
    status: str
    strategy: Optional[str]
    tags: Optional[list]
    entry_at: Optional[str]
    exit_at: Optional[str]
    created_at: str


@dataclass
class PortfolioPosition:
    ticker: str
    total_quantity: float
    avg_entry_price: float
    agent_count: int


@dataclass
class PortfolioSummary:
    positions: list  # List[PortfolioPosition]
    aggregate_stats: dict
    agents: list
```

Add `from typing import Optional` at the top if not already present.

- [ ] **Step 2: Commit**

```bash
git add sdk-python/remembr/models.py
git commit -m "feat(sdk): add dataclasses for risk, replay, signals, portfolio"
```

### Task 19: Add New Methods to TradingJournal

**Files:**
- Modify: `sdk-python/remembr/trading.py`

- [ ] **Step 1: Add signal, risk, replay, export, portfolio, and alert methods**

Add these methods to the `TradingJournal` class in `sdk-python/remembr/trading.py`:

```python
def get_signals(self, ticker: str = None, limit: int = 50) -> list:
    """Fetch copy-trading signals from broadcasting agents."""
    params = {"limit": limit}
    if ticker:
        params["ticker"] = ticker
    resp = self._client.get_path("/trading/signals", params=params)
    return resp.get("data", [])

def get_risk_metrics(self, market_prices: dict = None, paper: bool = None) -> list:
    """Get risk metrics for open positions with optional market prices."""
    params = {"paper": "true" if (paper if paper is not None else self._paper) else "false"}
    if market_prices:
        for ticker, price in market_prices.items():
            params[f"market_prices[{ticker}]"] = str(price)
    resp = self._client.get_path("/trading/risk", params=params)
    return resp.get("data", [])

def get_drawdown(self, paper: bool = None) -> dict:
    """Get max drawdown statistics."""
    p = paper if paper is not None else self._paper
    params = {"paper": "true" if p else "false"}
    resp = self._client.get_path("/trading/risk/drawdown", params=params)
    return resp.get("data", {})

def replay_trades(self, exit_overrides: dict = None, exit_offset_pct: float = None, paper: bool = None) -> dict:
    """Replay historical trades with alternative exit prices."""
    p = paper if paper is not None else self._paper
    body = {"paper": p}
    if exit_overrides:
        body["exit_overrides"] = exit_overrides
    if exit_offset_pct is not None:
        body["exit_offset_pct"] = exit_offset_pct
    resp = self._client.post_path("/trading/replay", json=body)
    return resp.get("data", {})

def export_trades(self, format: str = "json", paper: bool = None, **filters) -> any:
    """Export trades in JSON or CSV format."""
    p = paper if paper is not None else self._paper
    params = {"format": format, "paper": "true" if p else "false", **filters}
    resp = self._client.get_path("/trading/export", params=params)
    if format == "csv":
        return resp  # Raw CSV string
    return resp.get("data", [])

def get_portfolio(self, paper: bool = None) -> dict:
    """Get multi-agent portfolio aggregation."""
    p = paper if paper is not None else self._paper
    params = {"paper": "true" if p else "false"}
    resp = self._client.get_path("/trading/portfolio", params=params)
    return resp.get("data", {})

def create_alert(self, condition: str, ticker: str = None, threshold: float = None) -> dict:
    """Create a trade alert."""
    body = {"condition": condition}
    if ticker:
        body["ticker"] = ticker
    if threshold is not None:
        body["threshold"] = str(threshold)
    resp = self._client.post_path("/trading/alerts", json=body)
    return resp.get("data", {})

def list_alerts(self) -> list:
    """List all trade alerts."""
    resp = self._client.get_path("/trading/alerts")
    return resp.get("data", [])

def delete_alert(self, alert_id: str) -> None:
    """Delete a trade alert."""
    self._client.delete_path(f"/trading/alerts/{alert_id}")
```

- [ ] **Step 2: Commit**

```bash
git add sdk-python/remembr/trading.py
git commit -m "feat(sdk): add signal, risk, replay, export, portfolio, alert methods"
```

### Task 20: Add Python SDK Tests

**Files:**
- Create: `sdk-python/tests/test_signals.py`
- Create: `sdk-python/tests/test_risk.py`
- Create: `sdk-python/tests/test_replay.py`

- [ ] **Step 1: Create test_signals.py**

```python
from unittest.mock import MagicMock
from remembr.trading import TradingJournal


def test_get_signals_returns_list():
    client = MagicMock()
    client.get_path.return_value = {
        "data": [
            {"trade_id": "t1", "ticker": "AAPL", "direction": "long"},
            {"trade_id": "t2", "ticker": "TSLA", "direction": "short"},
        ]
    }

    journal = TradingJournal(client, paper=False)
    signals = journal.get_signals()

    assert len(signals) == 2
    assert signals[0]["ticker"] == "AAPL"
    client.get_path.assert_called_once_with("/trading/signals", params={"limit": 50})


def test_get_signals_filters_by_ticker():
    client = MagicMock()
    client.get_path.return_value = {"data": [{"trade_id": "t1", "ticker": "AAPL"}]}

    journal = TradingJournal(client, paper=False)
    journal.get_signals(ticker="AAPL")

    client.get_path.assert_called_once_with(
        "/trading/signals", params={"limit": 50, "ticker": "AAPL"}
    )
```

- [ ] **Step 2: Create test_risk.py**

```python
from unittest.mock import MagicMock
from remembr.trading import TradingJournal


def test_get_risk_metrics():
    client = MagicMock()
    client.get_path.return_value = {
        "data": [{"ticker": "AAPL", "unrealized_pnl": 100.0, "exposure": 1600.0}]
    }

    journal = TradingJournal(client, paper=False)
    result = journal.get_risk_metrics(market_prices={"AAPL": 160.0})

    assert len(result) == 1
    assert result[0]["unrealized_pnl"] == 100.0


def test_get_drawdown():
    client = MagicMock()
    client.get_path.return_value = {
        "data": {"max_drawdown": -50.0, "peak": 100.0, "trough": 50.0}
    }

    journal = TradingJournal(client, paper=False)
    result = journal.get_drawdown()

    assert result["max_drawdown"] == -50.0
```

- [ ] **Step 3: Create test_replay.py**

```python
from unittest.mock import MagicMock
from remembr.trading import TradingJournal


def test_replay_trades():
    client = MagicMock()
    client.post_path.return_value = {
        "data": {
            "total_trades": 5,
            "wins": 3,
            "losses": 2,
            "win_rate": 60.0,
            "total_pnl": 250.0,
            "trades": [],
        }
    }

    journal = TradingJournal(client, paper=False)
    result = journal.replay_trades(exit_offset_pct=-5.0)

    assert result["total_trades"] == 5
    assert result["total_pnl"] == 250.0
    client.post_path.assert_called_once_with(
        "/trading/replay",
        json={"paper": False, "exit_offset_pct": -5.0},
    )


def test_replay_with_overrides():
    client = MagicMock()
    client.post_path.return_value = {"data": {"total_trades": 1, "total_pnl": -100.0}}

    journal = TradingJournal(client, paper=False)
    result = journal.replay_trades(exit_overrides={"AAPL": "90.00"})

    assert result["total_pnl"] == -100.0
```

- [ ] **Step 4: Run Python tests**

Run: `cd sdk-python && python -m pytest tests/test_signals.py tests/test_risk.py tests/test_replay.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add sdk-python/tests/test_signals.py sdk-python/tests/test_risk.py sdk-python/tests/test_replay.py
git commit -m "feat(sdk): add tests for signals, risk, and replay methods"
```

---

## Final Verification

### Task 21: Full Regression Test

- [ ] **Step 1: Run all PHP tests**

Run: `php artisan test -v`
Expected: All tests PASS (existing + ~35 new tests)

- [ ] **Step 2: Run all Python tests**

Run: `cd sdk-python && python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Run style checks**

Run: `./vendor/bin/pint`
Expected: All files formatted

- [ ] **Step 4: Final commit if pint changed anything**

```bash
git add -A
git commit -m "style: format new trading feature code with Pint"
```

---

## Route Summary (all new endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/v1/trading/signals` | Yes | Copy-trading signal feed |
| GET | `/v1/trading/alerts` | Yes | List trade alerts |
| POST | `/v1/trading/alerts` | Yes | Create trade alert |
| DELETE | `/v1/trading/alerts/{id}` | Yes | Delete trade alert |
| GET | `/v1/trading/risk` | Yes | Position risk metrics |
| GET | `/v1/trading/risk/drawdown` | Yes | Max drawdown stats |
| GET | `/v1/trading/stats/correlations` | Yes | Ticker PnL correlations |
| GET | `/v1/trading/export` | Yes | Export trades (JSON/CSV) |
| POST | `/v1/trading/replay` | Yes | Trade replay/simulation |
| GET | `/v1/trading/portfolio` | Yes | Multi-agent portfolio |

## Webhook Events Added

| Event | Trigger | Payload |
|-------|---------|---------|
| `trade.opened` | New parent entry trade (live, listed agent) | Trade details |
| `trade.closed` | Parent trade fully closed (live, listed agent) | Trade + PnL |
| `position.changed` | Any trade/cancellation changes position | Position state |
| `alert.triggered` | Alert condition matched | Alert + trade details |
