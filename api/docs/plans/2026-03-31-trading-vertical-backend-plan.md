# Trading Vertical Backend Implementation Plan

> **For Gemini:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Trading Journal Layer (Models, Migrations, Observers, API Endpoints) in the Remembr Laravel backend to support AI trading agents.

**Architecture:** A RESTful layer on top of the existing memory system. The system centers on an append-only `trades` ledger. `TradeObserver` handles the complex state transitions (PnL calculation, partial closes, updating denormalized `positions` and `trading_stats`).

**Tech Stack:** Laravel, PHP 8, PostgreSQL/MySQL, Pest (Testing)

---

### Task 1: Database Migrations

**Files:**
- Create: `database/migrations/xxxx_xx_xx_xxxxxx_create_trading_tables.php`

**Step 1: Write the migration**
Create the migration file for `trades`, `positions`, and `trading_stats` tables according to the spec.

```php
// Example migration skeleton
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void {
        Schema::create('trades', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('agent_id')->constrained('agents');
            $table->uuid('parent_trade_id')->nullable();
            $table->string('ticker', 64);
            $table->enum('direction', ['long', 'short']);
            $table->decimal('entry_price', 24, 8);
            $table->decimal('exit_price', 24, 8)->nullable();
            $table->decimal('quantity', 24, 8);
            $table->decimal('fees', 24, 8)->default(0);
            $table->timestamp('entry_at');
            $table->timestamp('exit_at')->nullable();
            $table->enum('status', ['open', 'closed', 'cancelled'])->default('open');
            $table->decimal('pnl', 24, 8)->nullable();
            $table->decimal('pnl_percent', 8, 4)->nullable();
            $table->string('strategy')->nullable();
            $table->float('confidence')->nullable();
            $table->boolean('paper')->default(true);
            $table->uuid('decision_memory_id')->nullable();
            $table->uuid('outcome_memory_id')->nullable();
            $table->jsonb('metadata')->nullable();
            $table->timestamps();

            $table->index(['agent_id', 'status']);
            $table->index(['agent_id', 'ticker', 'paper']);
            $table->index('parent_trade_id');
            $table->index('strategy');
        });

        // Add positions and trading_stats similarly...
    }

    public function down(): void {
        Schema::dropIfExists('trading_stats');
        Schema::dropIfExists('positions');
        Schema::dropIfExists('trades');
    }
};
```

**Step 2: Run the migration to verify**
Run: `php artisan migrate`
Expected: Migration runs successfully.

**Step 3: Commit**
```bash
git add database/migrations/
git commit -m "feat(trading): add migrations for trades, positions, and stats"
```

---

### Task 2: Eloquent Models

**Files:**
- Create: `app/Models/Trade.php`
- Create: `app/Models/Position.php`
- Create: `app/Models/TradingStats.php`

**Step 1: Write the `Trade` model**
```php
namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Trade extends Model
{
    use HasUuids;

    protected $guarded = [];

    protected $casts = [
        'entry_at' => 'datetime',
        'exit_at' => 'datetime',
        'paper' => 'boolean',
        'metadata' => 'array',
    ];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }

    public function parent(): BelongsTo
    {
        return $this->belongsTo(Trade::class, 'parent_trade_id');
    }

    public function children(): HasMany
    {
        return $this->hasMany(Trade::class, 'parent_trade_id');
    }
}
```

**Step 2: Write `Position` and `TradingStats` models similarly**
Ensure UUID traits, guarded properties, and relationships are set up.

**Step 3: Commit**
```bash
git add app/Models/
git commit -m "feat(trading): create models for trades, positions, and stats"
```

---

### Task 3: TradingService & PnL Logic

**Files:**
- Create: `app/Services/TradingService.php`
- Create: `tests/Unit/TradingServiceTest.php`

**Step 1: Write failing test for PnL calculation**
```php
// tests/Unit/TradingServiceTest.php
test('calculates long trade pnl correctly', function () {
    $parent = new Trade(['direction' => 'long', 'entry_price' => 100, 'quantity' => 10]);
    $child = new Trade(['direction' => 'short', 'entry_price' => 110, 'quantity' => 10, 'fees' => 5]);
    
    $pnl = app(TradingService::class)->calculateChildPnL($parent, $child);
    
    expect($pnl)->toBe(95.0); // (110 - 100) * 10 - 5
});
```

**Step 2: Run test to verify it fails**
Run: `php artisan test --filter=TradingServiceTest`
Expected: FAIL due to missing `TradingService` and `calculateChildPnL`.

**Step 3: Implement `TradingService`**
```php
// app/Services/TradingService.php
namespace App\Services;
use App\Models\Trade;

class TradingService
{
    public function calculateChildPnL(Trade $parent, Trade $child): float
    {
        $priceDiff = $parent->direction === 'long' 
            ? $child->entry_price - $parent->entry_price 
            : $parent->entry_price - $child->entry_price;
            
        return ($priceDiff * $child->quantity) - $child->fees;
    }
}
```

**Step 4: Run test to verify passes**
Run: `php artisan test --filter=TradingServiceTest`
Expected: PASS.

**Step 5: Commit**
```bash
git add app/Services/ tests/Unit/
git commit -m "feat(trading): add TradingService with PnL calculation"
```

---

### Task 4: TradeObserver & Queued Stats

**Files:**
- Create: `app/Observers/TradeObserver.php`
- Create: `app/Jobs/RecalculateTradingStats.php`
- Modify: `app/Providers/AppServiceProvider.php` to register observer
- Create: `tests/Feature/TradeObserverTest.php`

**Step 1: Implement Queued Stats Recalculation**
The `TradeObserver` should dispatch `RecalculateTradingStats` instead of doing it synchronously to ensure API responsiveness.

```php
// app/Jobs/RecalculateTradingStats.php
public function handle(): void {
    // Heavy aggregation logic here for a given agent
}
```

**Step 2: Implement TradeObserver**
```php
namespace App\Observers;
use App\Models\Trade;
use App\Services\TradingService;
use App\Jobs\RecalculateTradingStats;

class TradeObserver
{
    public function created(Trade $trade)
    {
        if ($trade->parent_trade_id) {
            // It's a close execution
            $parent = $trade->parent;
            $service = app(TradingService::class);
            
            $trade->pnl = $service->calculateChildPnL($parent, $trade);
            $trade->saveQuietly();
            
            // ... update parent ...
            
            RecalculateTradingStats::dispatch($trade->agent_id, $trade->paper);
        }
    }
}
```

**Step 3: Commit**
```bash
git add app/Observers/ app/Jobs/ app/Providers/
git commit -m "feat(trading): implement TradeObserver with queued stats recalculation"
```

---

### Task 5: Trading Controllers & API Routes

**Files:**
- Create: `app/Http/Controllers/Api/TradingController.php`
- Modify: `routes/api.php`
- Create: `tests/Feature/TradingApiTest.php`

**Step 1: Write test for creating a trade**
```php
test('agent can record a trade entry via api', function () {
    $response = $this->postJson('/api/v1/trading/trades', [
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => 150,
        'quantity' => 10,
        'entry_at' => now()->toIso8601String(),
    ]);
    
    $response->assertStatus(201);
});
```

**Step 2: Add Route & Implement Controller**
```php
Route::middleware('auth:sanctum')->prefix('v1/trading')->group(function () {
    Route::post('/trades', [TradingController::class, 'store']);
});
```

**Step 3: Commit**
```bash
git add app/Http/Controllers/ routes/api.php
git commit -m "feat(trading): add trades REST endpoints"
```

---

### Task 6: Paginated Equity Curve

**Files:**
- Create: `app/Http/Controllers/Api/TradingStatsController.php`
- Test: `tests/Feature/TradingStatsApiTest.php`

**Step 1: Implement Cursor-Paginated Equity Curve**
```php
// app/Http/Controllers/Api/TradingStatsController.php
public function equityCurve(Request $request) {
    return Trade::where('agent_id', $request->user()->id)
        ->where('status', 'closed')
        ->orderBy('exit_at')
        ->cursorPaginate(50);
}
```

**Step 2: Commit**
```bash
git add app/Http/Controllers/
git commit -m "feat(trading): add cursor-paginated equity curve endpoint"
```
