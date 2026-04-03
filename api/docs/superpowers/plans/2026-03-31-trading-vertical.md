# Trading Vertical Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a trading journal layer on top of Remembr's memory system — trades, positions, performance stats, and a public leaderboard — so AI trading agents can journal decisions, track PnL, and showcase their reasoning.

**Architecture:** Append-only ledger where every execution (entry or exit) is a `POST`. Exits link to parent entries via `parent_trade_id`. A `TradeObserver` computes PnL, updates positions and stats on every trade creation. Trading data links back to the memory system via FK references to decision/outcome memories.

**Tech Stack:** Laravel 12 / PHP 8.3 / PostgreSQL / Pest tests / Existing agent auth middleware

**Spec:** `docs/superpowers/specs/2026-03-31-trading-vertical-design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `database/migrations/2026_03_31_000001_create_trades_table.php` | Trades schema with soft deletes |
| `database/migrations/2026_03_31_000002_create_positions_table.php` | Positions schema |
| `database/migrations/2026_03_31_000003_create_trading_stats_table.php` | Trading stats schema |
| `database/factories/TradeFactory.php` | Factory for test trades |
| `app/Models/Trade.php` | Trade model with scopes and relationships |
| `app/Models/Position.php` | Position model |
| `app/Models/TradingStats.php` | Trading stats model |
| `app/Services/TradingService.php` | PnL computation, stats recalculation, position aggregation |
| `app/Observers/TradeObserver.php` | Fires on created/updated, orchestrates PnL + stats + achievements |
| `app/Http/Controllers/Api/TradingController.php` | Trade CRUD endpoints |
| `app/Http/Controllers/Api/TradingPositionController.php` | Position read endpoints |
| `app/Http/Controllers/Api/TradingStatsController.php` | Stats + analytics endpoints |
| `app/Http/Controllers/Api/TradingLeaderboardController.php` | Public leaderboard + profiles |
| `tests/Feature/TradingApiTest.php` | Full endpoint + observer coverage |
| `tests/Unit/TradingServiceTest.php` | PnL and stats computation unit tests |

### Modified Files
| File | Change |
|------|--------|
| `app/Models/Agent.php` | Add `trades()`, `positions()`, `tradingStats()` relationships |
| `app/Services/AchievementService.php` | Add trading achievement definitions + checkers |
| `app/Providers/AppServiceProvider.php` | Register `TradeObserver` |
| `routes/api.php` | Add `/v1/trading/*` routes |

---

## Task 1: Database Migrations

**Files:**
- Create: `database/migrations/2026_03_31_000001_create_trades_table.php`
- Create: `database/migrations/2026_03_31_000002_create_positions_table.php`
- Create: `database/migrations/2026_03_31_000003_create_trading_stats_table.php`

- [ ] **Step 1: Create the trades migration**

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('trades', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('agent_id')->constrained()->cascadeOnDelete();
            $table->foreignUuid('parent_trade_id')->nullable()->constrained('trades')->nullOnDelete();
            $table->string('ticker', 64);
            $table->string('direction'); // long, short
            $table->decimal('entry_price', 24, 8);
            $table->decimal('exit_price', 24, 8)->nullable();
            $table->decimal('quantity', 24, 8);
            $table->decimal('fees', 24, 8)->default(0);
            $table->timestamp('entry_at');
            $table->timestamp('exit_at')->nullable();
            $table->string('status')->default('open'); // open, closed, cancelled
            $table->decimal('pnl', 24, 8)->nullable();
            $table->decimal('pnl_percent', 8, 4)->nullable();
            $table->string('strategy')->nullable();
            $table->float('confidence')->nullable();
            $table->boolean('paper')->default(true);
            $table->foreignUuid('decision_memory_id')->nullable()->constrained('memories')->nullOnDelete();
            $table->foreignUuid('outcome_memory_id')->nullable()->constrained('memories')->nullOnDelete();
            $table->jsonb('metadata')->nullable();
            $table->softDeletes();
            $table->timestamps();

            $table->index(['agent_id', 'status']);
            $table->index(['agent_id', 'ticker', 'paper']);
            $table->index(['agent_id', 'paper', 'created_at']);
            $table->index('parent_trade_id');
            $table->index('strategy');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('trades');
    }
};
```

- [ ] **Step 2: Create the positions migration**

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('positions', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('agent_id')->constrained()->cascadeOnDelete();
            $table->string('ticker', 64);
            $table->boolean('paper')->default(true);
            $table->decimal('quantity', 24, 8)->default(0);
            $table->decimal('avg_entry_price', 24, 8)->default(0);
            $table->timestamps();

            $table->unique(['agent_id', 'ticker', 'paper']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('positions');
    }
};
```

- [ ] **Step 3: Create the trading_stats migration**

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('trading_stats', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('agent_id')->constrained()->cascadeOnDelete();
            $table->boolean('paper')->default(true);
            $table->integer('total_trades')->default(0);
            $table->integer('win_count')->default(0);
            $table->integer('loss_count')->default(0);
            $table->decimal('win_rate', 5, 2)->nullable();
            $table->decimal('profit_factor', 10, 4)->nullable();
            $table->decimal('total_pnl', 24, 8)->default(0);
            $table->decimal('avg_pnl_percent', 8, 4)->nullable();
            $table->decimal('best_trade_pnl', 24, 8)->nullable();
            $table->decimal('worst_trade_pnl', 24, 8)->nullable();
            $table->decimal('sharpe_ratio', 8, 4)->nullable();
            $table->integer('current_streak')->default(0);
            $table->timestamps();

            $table->unique(['agent_id', 'paper']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('trading_stats');
    }
};
```

- [ ] **Step 4: Run the migrations**

Run: `php artisan migrate`
Expected: All 3 tables created successfully.

- [ ] **Step 5: Commit**

```bash
git add database/migrations/2026_03_31_*
git commit -m "feat(trading): add trades, positions, trading_stats migrations"
```

---

## Task 2: Models + Factory

**Files:**
- Create: `app/Models/Trade.php`
- Create: `app/Models/Position.php`
- Create: `app/Models/TradingStats.php`
- Create: `database/factories/TradeFactory.php`
- Modify: `app/Models/Agent.php`

- [ ] **Step 1: Create the Trade model**

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;

class Trade extends Model
{
    use HasFactory, HasUuids, SoftDeletes;

    const DIRECTIONS = ['long', 'short'];
    const STATUSES = ['open', 'closed', 'cancelled'];

    protected $fillable = [
        'agent_id',
        'parent_trade_id',
        'ticker',
        'direction',
        'entry_price',
        'exit_price',
        'quantity',
        'fees',
        'entry_at',
        'exit_at',
        'status',
        'pnl',
        'pnl_percent',
        'strategy',
        'confidence',
        'paper',
        'decision_memory_id',
        'outcome_memory_id',
        'metadata',
    ];

    protected $casts = [
        'entry_price' => 'decimal:8',
        'exit_price' => 'decimal:8',
        'quantity' => 'decimal:8',
        'fees' => 'decimal:8',
        'pnl' => 'decimal:8',
        'pnl_percent' => 'decimal:4',
        'confidence' => 'float',
        'paper' => 'boolean',
        'metadata' => 'array',
        'entry_at' => 'datetime',
        'exit_at' => 'datetime',
    ];

    // Relationships

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }

    public function parentTrade(): BelongsTo
    {
        return $this->belongsTo(Trade::class, 'parent_trade_id');
    }

    public function children(): HasMany
    {
        return $this->hasMany(Trade::class, 'parent_trade_id');
    }

    public function decisionMemory(): BelongsTo
    {
        return $this->belongsTo(Memory::class, 'decision_memory_id');
    }

    public function outcomeMemory(): BelongsTo
    {
        return $this->belongsTo(Memory::class, 'outcome_memory_id');
    }

    // Scopes

    public function scopeForAgent(Builder $query, Agent $agent): Builder
    {
        return $query->where('agent_id', $agent->id);
    }

    public function scopeOpen(Builder $query): Builder
    {
        return $query->where('status', 'open');
    }

    public function scopeClosed(Builder $query): Builder
    {
        return $query->where('status', 'closed');
    }

    public function scopeParentsOnly(Builder $query): Builder
    {
        return $query->whereNull('parent_trade_id');
    }

    public function scopePaper(Builder $query, bool $paper = true): Builder
    {
        return $query->where('paper', $paper);
    }

    // Helpers

    public function oppositeDirection(): string
    {
        return $this->direction === 'long' ? 'short' : 'long';
    }

    public function remainingQuantity(): string
    {
        $childrenQty = $this->children()->sum('quantity');
        return bcsub($this->quantity, $childrenQty, 8);
    }
}
```

- [ ] **Step 2: Create the Position model**

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Position extends Model
{
    use HasUuids;

    protected $fillable = [
        'agent_id',
        'ticker',
        'paper',
        'quantity',
        'avg_entry_price',
    ];

    protected $casts = [
        'quantity' => 'decimal:8',
        'avg_entry_price' => 'decimal:8',
        'paper' => 'boolean',
    ];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }
}
```

- [ ] **Step 3: Create the TradingStats model**

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class TradingStats extends Model
{
    use HasUuids;

    protected $fillable = [
        'agent_id',
        'paper',
        'total_trades',
        'win_count',
        'loss_count',
        'win_rate',
        'profit_factor',
        'total_pnl',
        'avg_pnl_percent',
        'best_trade_pnl',
        'worst_trade_pnl',
        'sharpe_ratio',
        'current_streak',
    ];

    protected $casts = [
        'paper' => 'boolean',
        'win_rate' => 'decimal:2',
        'profit_factor' => 'decimal:4',
        'total_pnl' => 'decimal:8',
        'avg_pnl_percent' => 'decimal:4',
        'best_trade_pnl' => 'decimal:8',
        'worst_trade_pnl' => 'decimal:8',
        'sharpe_ratio' => 'decimal:4',
    ];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }
}
```

- [ ] **Step 4: Create the TradeFactory**

```php
<?php

namespace Database\Factories;

use App\Models\Agent;
use App\Models\Trade;
use Illuminate\Database\Eloquent\Factories\Factory;

class TradeFactory extends Factory
{
    protected $model = Trade::class;

    public function definition(): array
    {
        return [
            'agent_id' => Agent::factory(),
            'ticker' => $this->faker->randomElement(['AAPL', 'TSLA', 'GOOG', 'BTC-USD']),
            'direction' => 'long',
            'entry_price' => $this->faker->randomFloat(8, 10, 500),
            'quantity' => $this->faker->randomFloat(8, 1, 100),
            'fees' => 0,
            'entry_at' => now(),
            'status' => 'open',
            'paper' => true,
        ];
    }

    public function short(): static
    {
        return $this->state(['direction' => 'short']);
    }

    public function closed(): static
    {
        return $this->state([
            'status' => 'closed',
            'exit_price' => $this->faker->randomFloat(8, 10, 500),
            'exit_at' => now(),
        ]);
    }

    public function live(): static
    {
        return $this->state(['paper' => false]);
    }
}
```

- [ ] **Step 5: Add relationships to Agent model**

In `app/Models/Agent.php`, add these three methods:

```php
public function trades(): HasMany
{
    return $this->hasMany(Trade::class);
}

public function positions(): HasMany
{
    return $this->hasMany(Position::class);
}

public function tradingStats(): HasOne
{
    return $this->hasOne(TradingStats::class);
}
```

Add `use App\Models\Trade;`, `use App\Models\Position;`, and `use App\Models\TradingStats;` to the imports. The `HasOne` import already exists.

- [ ] **Step 6: Commit**

```bash
git add app/Models/Trade.php app/Models/Position.php app/Models/TradingStats.php database/factories/TradeFactory.php app/Models/Agent.php
git commit -m "feat(trading): add Trade, Position, TradingStats models + factory"
```

---

## Task 3: TradingService — PnL Computation + Stats

**Files:**
- Create: `app/Services/TradingService.php`
- Create: `tests/Unit/TradingServiceTest.php`

- [ ] **Step 1: Write failing tests for PnL computation**

Create `tests/Unit/TradingServiceTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\Trade;
use App\Services\TradingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

describe('PnL Computation', function () {
    it('computes PnL for a long entry closed by a short exit', function () {
        $service = app(TradingService::class);
        $agent = makeAgent(makeOwner());

        $parent = Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => '100.00000000',
            'quantity' => '10.00000000',
            'fees' => '0.00000000',
            'paper' => true,
        ]);

        $child = Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'short',
            'entry_price' => '110.00000000',
            'quantity' => '10.00000000',
            'fees' => '0.00000000',
            'parent_trade_id' => $parent->id,
            'paper' => true,
        ]);

        $pnl = $service->computeChildPnl($child, $parent);

        expect($pnl['pnl'])->toBe('100.00000000');
        expect($pnl['pnl_percent'])->toBe('10.0000');
    });

    it('computes PnL for a short entry closed by a long exit', function () {
        $service = app(TradingService::class);
        $agent = makeAgent(makeOwner());

        $parent = Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'short',
            'entry_price' => '100.00000000',
            'quantity' => '10.00000000',
            'fees' => '0.00000000',
            'paper' => true,
        ]);

        $child = Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => '90.00000000',
            'quantity' => '10.00000000',
            'fees' => '0.00000000',
            'parent_trade_id' => $parent->id,
            'paper' => true,
        ]);

        $pnl = $service->computeChildPnl($child, $parent);

        expect($pnl['pnl'])->toBe('100.00000000');
        expect($pnl['pnl_percent'])->toBe('10.0000');
    });

    it('deducts fees from PnL', function () {
        $service = app(TradingService::class);
        $agent = makeAgent(makeOwner());

        $parent = Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => '100.00000000',
            'quantity' => '10.00000000',
            'fees' => '5.00000000',
            'paper' => true,
        ]);

        $child = Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'short',
            'entry_price' => '110.00000000',
            'quantity' => '10.00000000',
            'fees' => '5.00000000',
            'parent_trade_id' => $parent->id,
            'paper' => true,
        ]);

        $pnl = $service->computeChildPnl($child, $parent);

        // (110-100)*10 - 5(parent) - 5(child) = 90
        expect($pnl['pnl'])->toBe('90.00000000');
    });
});

describe('Stats Recalculation', function () {
    it('recalculates stats from closed parent trades', function () {
        $service = app(TradingService::class);
        $agent = makeAgent(makeOwner());

        // Create 3 closed parent trades: 2 wins, 1 loss
        Trade::factory()->create([
            'agent_id' => $agent->id,
            'direction' => 'long',
            'entry_price' => '100.00000000',
            'quantity' => '10.00000000',
            'status' => 'closed',
            'pnl' => '100.00000000',
            'pnl_percent' => '10.0000',
            'entry_at' => now()->subDays(3),
            'paper' => true,
        ]);

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'direction' => 'long',
            'entry_price' => '200.00000000',
            'quantity' => '5.00000000',
            'status' => 'closed',
            'pnl' => '50.00000000',
            'pnl_percent' => '5.0000',
            'entry_at' => now()->subDays(2),
            'paper' => true,
        ]);

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'direction' => 'long',
            'entry_price' => '150.00000000',
            'quantity' => '10.00000000',
            'status' => 'closed',
            'pnl' => '-30.00000000',
            'pnl_percent' => '-2.0000',
            'entry_at' => now()->subDays(1),
            'paper' => true,
        ]);

        $service->recalculateStats($agent, paper: true);

        $stats = $agent->tradingStats()->where('paper', true)->first();

        expect($stats->total_trades)->toBe(3);
        expect($stats->win_count)->toBe(2);
        expect($stats->loss_count)->toBe(1);
        expect((float) $stats->win_rate)->toBe(66.67);
        expect((float) $stats->total_pnl)->toBe(120.0);
        expect((float) $stats->best_trade_pnl)->toBe(100.0);
        expect((float) $stats->worst_trade_pnl)->toBe(-30.0);
        // current_streak: last trade was a loss, so -1
        expect($stats->current_streak)->toBe(-1);
    });

    it('handles profit_factor with zero losses', function () {
        $service = app(TradingService::class);
        $agent = makeAgent(makeOwner());

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'status' => 'closed',
            'pnl' => '100.00000000',
            'pnl_percent' => '10.0000',
            'entry_at' => now(),
            'paper' => true,
        ]);

        $service->recalculateStats($agent, paper: true);

        $stats = $agent->tradingStats()->where('paper', true)->first();

        expect($stats->profit_factor)->toBeNull();
    });
});

describe('Position Recalculation', function () {
    it('aggregates open entry trades into positions', function () {
        $service = app(TradingService::class);
        $agent = makeAgent(makeOwner());

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => '100.00000000',
            'quantity' => '10.00000000',
            'status' => 'open',
            'paper' => true,
        ]);

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => '110.00000000',
            'quantity' => '10.00000000',
            'status' => 'open',
            'paper' => true,
        ]);

        $service->recalculatePosition($agent, 'AAPL', paper: true);

        $position = $agent->positions()->where('ticker', 'AAPL')->where('paper', true)->first();

        expect((float) $position->quantity)->toBe(20.0);
        expect((float) $position->avg_entry_price)->toBe(105.0);
    });

    it('removes position when no open trades remain', function () {
        $service = app(TradingService::class);
        $agent = makeAgent(makeOwner());

        // Only a closed trade
        Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'status' => 'closed',
            'paper' => true,
        ]);

        $service->recalculatePosition($agent, 'AAPL', paper: true);

        $position = $agent->positions()->where('ticker', 'AAPL')->where('paper', true)->first();

        expect($position)->toBeNull();
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `php artisan test tests/Unit/TradingServiceTest.php`
Expected: FAIL — `TradingService` class not found.

- [ ] **Step 3: Implement TradingService**

Create `app/Services/TradingService.php`:

```php
<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Position;
use App\Models\Trade;
use App\Models\TradingStats;

class TradingService
{
    /**
     * Compute PnL for a child trade based on its parent.
     *
     * @return array{pnl: string, pnl_percent: string}
     */
    public function computeChildPnl(Trade $child, Trade $parent): array
    {
        if ($parent->direction === 'long') {
            // Long entry, short exit: profit when exit > entry
            $grossPnl = bcmul(bcsub($child->entry_price, $parent->entry_price, 8), $child->quantity, 8);
        } else {
            // Short entry, long exit: profit when entry > exit
            $grossPnl = bcmul(bcsub($parent->entry_price, $child->entry_price, 8), $child->quantity, 8);
        }

        $totalFees = bcadd($parent->fees, $child->fees, 8);
        $netPnl = bcsub($grossPnl, $totalFees, 8);

        $costBasis = bcmul($parent->entry_price, $child->quantity, 8);
        $pnlPercent = $costBasis > 0
            ? bcmul(bcdiv($netPnl, $costBasis, 8), '100', 4)
            : '0.0000';

        return [
            'pnl' => $netPnl,
            'pnl_percent' => $pnlPercent,
        ];
    }

    /**
     * After a child trade is created, update the parent with aggregated PnL
     * and potentially close it.
     */
    public function processChildTrade(Trade $child, Trade $parent): void
    {
        $pnl = $this->computeChildPnl($child, $parent);

        $child->updateQuietly([
            'pnl' => $pnl['pnl'],
            'pnl_percent' => $pnl['pnl_percent'],
        ]);

        // Aggregate PnL across all children onto parent
        $totalChildPnl = $parent->children()->sum('pnl');
        $totalChildQty = $parent->children()->sum('quantity');

        $costBasis = bcmul($parent->entry_price, $parent->quantity, 8);
        $parentPnlPercent = $costBasis > 0
            ? bcmul(bcdiv((string) $totalChildPnl, $costBasis, 8), '100', 4)
            : '0.0000';

        $parentUpdate = [
            'pnl' => (string) $totalChildPnl,
            'pnl_percent' => $parentPnlPercent,
        ];

        // Check if fully closed
        if (bccomp((string) $totalChildQty, $parent->quantity, 8) >= 0) {
            // Weighted average exit price from children
            $weightedExitSum = '0';
            foreach ($parent->children as $c) {
                $weightedExitSum = bcadd($weightedExitSum, bcmul($c->entry_price, $c->quantity, 8), 8);
            }
            $weightedExitPrice = bcdiv($weightedExitSum, (string) $totalChildQty, 8);

            $parentUpdate['status'] = 'closed';
            $parentUpdate['exit_price'] = $weightedExitPrice;
            $parentUpdate['exit_at'] = $child->entry_at;
        }

        $parent->updateQuietly($parentUpdate);
    }

    /**
     * Recalculate the position for a given agent/ticker/paper combo.
     */
    public function recalculatePosition(Agent $agent, string $ticker, bool $paper): void
    {
        $openEntries = Trade::where('agent_id', $agent->id)
            ->where('ticker', $ticker)
            ->where('paper', $paper)
            ->where('status', 'open')
            ->whereNull('parent_trade_id')
            ->get();

        if ($openEntries->isEmpty()) {
            Position::where('agent_id', $agent->id)
                ->where('ticker', $ticker)
                ->where('paper', $paper)
                ->delete();
            return;
        }

        $totalQty = '0';
        $totalCost = '0';

        foreach ($openEntries as $entry) {
            $remainingQty = $entry->remainingQuantity();
            $totalQty = bcadd($totalQty, $remainingQty, 8);
            $totalCost = bcadd($totalCost, bcmul($entry->entry_price, $remainingQty, 8), 8);
        }

        $avgPrice = bccomp($totalQty, '0', 8) > 0
            ? bcdiv($totalCost, $totalQty, 8)
            : '0.00000000';

        Position::updateOrCreate(
            [
                'agent_id' => $agent->id,
                'ticker' => $ticker,
                'paper' => $paper,
            ],
            [
                'quantity' => $totalQty,
                'avg_entry_price' => $avgPrice,
            ]
        );
    }

    /**
     * Recalculate aggregate trading stats for an agent.
     */
    public function recalculateStats(Agent $agent, bool $paper): void
    {
        $closedTrades = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->orderBy('entry_at')
            ->get();

        $totalTrades = $closedTrades->count();

        if ($totalTrades === 0) {
            TradingStats::updateOrCreate(
                ['agent_id' => $agent->id, 'paper' => $paper],
                [
                    'total_trades' => 0,
                    'win_count' => 0,
                    'loss_count' => 0,
                    'win_rate' => null,
                    'profit_factor' => null,
                    'total_pnl' => 0,
                    'avg_pnl_percent' => null,
                    'best_trade_pnl' => null,
                    'worst_trade_pnl' => null,
                    'sharpe_ratio' => null,
                    'current_streak' => 0,
                ]
            );
            return;
        }

        $winCount = $closedTrades->filter(fn ($t) => bccomp($t->pnl, '0', 8) > 0)->count();
        $lossCount = $closedTrades->filter(fn ($t) => bccomp($t->pnl, '0', 8) < 0)->count();
        $winRate = round(($winCount / $totalTrades) * 100, 2);

        $totalPnl = $closedTrades->reduce(fn ($carry, $t) => bcadd($carry ?? '0', $t->pnl, 8), '0');
        $avgPnlPercent = $closedTrades->avg('pnl_percent');

        $grossProfit = $closedTrades
            ->filter(fn ($t) => bccomp($t->pnl, '0', 8) > 0)
            ->reduce(fn ($carry, $t) => bcadd($carry ?? '0', $t->pnl, 8), '0');

        $grossLoss = $closedTrades
            ->filter(fn ($t) => bccomp($t->pnl, '0', 8) < 0)
            ->reduce(fn ($carry, $t) => bcadd($carry ?? '0', $t->pnl, 8), '0');

        $absGrossLoss = bcmul($grossLoss, '-1', 8);
        $profitFactor = bccomp($absGrossLoss, '0', 8) > 0
            ? bcdiv($grossProfit, $absGrossLoss, 4)
            : null;

        $bestPnl = $closedTrades->max('pnl');
        $worstPnl = $closedTrades->min('pnl');

        // Current streak: iterate from most recent
        $streak = 0;
        $reversed = $closedTrades->reverse();
        $streakDirection = null;
        foreach ($reversed as $trade) {
            $isWin = bccomp($trade->pnl, '0', 8) > 0;
            if ($streakDirection === null) {
                $streakDirection = $isWin;
            }
            if ($isWin === $streakDirection) {
                $streak++;
            } else {
                break;
            }
        }
        if ($streakDirection === false) {
            $streak = -$streak;
        }

        // Sharpe ratio (annualized, if >= 30 trades)
        $sharpe = null;
        if ($totalTrades >= 30) {
            $returns = $closedTrades->pluck('pnl_percent')->map(fn ($v) => (float) $v);
            $avgReturn = $returns->avg();
            $stdDev = sqrt($returns->map(fn ($r) => pow($r - $avgReturn, 2))->avg());
            if ($stdDev > 0) {
                $sharpe = round(($avgReturn / $stdDev) * sqrt(252), 4);
            }
        }

        TradingStats::updateOrCreate(
            ['agent_id' => $agent->id, 'paper' => $paper],
            [
                'total_trades' => $totalTrades,
                'win_count' => $winCount,
                'loss_count' => $lossCount,
                'win_rate' => $winRate,
                'profit_factor' => $profitFactor,
                'total_pnl' => $totalPnl,
                'avg_pnl_percent' => round($avgPnlPercent, 4),
                'best_trade_pnl' => $bestPnl,
                'worst_trade_pnl' => $worstPnl,
                'sharpe_ratio' => $sharpe,
                'current_streak' => $streak,
            ]
        );
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `php artisan test tests/Unit/TradingServiceTest.php`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/Services/TradingService.php tests/Unit/TradingServiceTest.php
git commit -m "feat(trading): add TradingService with PnL, stats, and position logic"
```

---

## Task 4: TradeObserver

**Files:**
- Create: `app/Observers/TradeObserver.php`
- Modify: `app/Providers/AppServiceProvider.php`

- [ ] **Step 1: Create TradeObserver**

```php
<?php

namespace App\Observers;

use App\Models\Trade;
use App\Services\AchievementService;
use App\Services\TradingService;

class TradeObserver
{
    public function __construct(
        private readonly TradingService $tradingService,
        private readonly AchievementService $achievements,
    ) {}

    public function created(Trade $trade): void
    {
        if ($trade->parent_trade_id) {
            $parent = $trade->parentTrade;
            $this->tradingService->processChildTrade($trade, $parent);
            $this->tradingService->recalculateStats($trade->agent, $trade->paper);
        }

        $this->tradingService->recalculatePosition(
            $trade->agent,
            $trade->ticker,
            $trade->paper,
        );

        $this->achievements->checkAndAward($trade->agent, 'trade');
    }

    public function updated(Trade $trade): void
    {
        if ($trade->wasChanged('status') && $trade->status === 'cancelled') {
            $this->tradingService->recalculatePosition(
                $trade->agent,
                $trade->ticker,
                $trade->paper,
            );
            $this->tradingService->recalculateStats($trade->agent, $trade->paper);
        }
    }
}
```

- [ ] **Step 2: Register the observer in AppServiceProvider**

In `app/Providers/AppServiceProvider.php`, add to the `boot()` method:

```php
\App\Models\Trade::observe(\App\Observers\TradeObserver::class);
```

- [ ] **Step 3: Commit**

```bash
git add app/Observers/TradeObserver.php app/Providers/AppServiceProvider.php
git commit -m "feat(trading): add TradeObserver for PnL, positions, stats"
```

---

## Task 5: TradingController — Trade CRUD

**Files:**
- Create: `app/Http/Controllers/Api/TradingController.php`
- Modify: `routes/api.php`
- Create: `tests/Feature/TradingApiTest.php` (first batch of tests)

- [ ] **Step 1: Write failing tests for trade creation and listing**

Create `tests/Feature/TradingApiTest.php`:

```php
<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\Trade;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        $mock->shouldReceive('embedBatch')->andReturn([array_fill(0, 1536, 0.1)]);
    });
});

// ---------------------------------------------------------------------------
// POST /v1/trading/trades — Record a trade
// ---------------------------------------------------------------------------

describe('POST /v1/trading/trades', function () {
    it('creates an entry trade', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/trading/trades', [
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => 185.50,
            'quantity' => 100,
            'entry_at' => '2026-03-31T14:30:00Z',
            'strategy' => 'momentum',
            'confidence' => 0.85,
            'paper' => true,
            'fees' => 1.50,
        ], withAgent($agent));

        $response->assertCreated()
            ->assertJsonFragment([
                'ticker' => 'AAPL',
                'direction' => 'long',
                'status' => 'open',
            ]);

        $this->assertDatabaseHas('trades', [
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'long',
        ]);
    });

    it('closes a parent trade when exit quantity matches', function () {
        $agent = makeAgent(makeOwner());

        $parent = Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => '100.00000000',
            'quantity' => '10.00000000',
            'paper' => true,
        ]);

        $response = $this->postJson('/api/v1/trading/trades', [
            'ticker' => 'AAPL',
            'direction' => 'short',
            'entry_price' => 110.00,
            'quantity' => 10,
            'entry_at' => '2026-03-31T16:00:00Z',
            'parent_trade_id' => $parent->id,
            'paper' => true,
        ], withAgent($agent));

        $response->assertCreated();

        // Parent should now be closed
        $parent->refresh();
        expect($parent->status)->toBe('closed');
        expect((float) $parent->pnl)->toBeGreaterThan(0);
    });

    it('rejects exit with same direction as parent', function () {
        $agent = makeAgent(makeOwner());

        $parent = Trade::factory()->create([
            'agent_id' => $agent->id,
            'direction' => 'long',
            'paper' => true,
        ]);

        $response = $this->postJson('/api/v1/trading/trades', [
            'ticker' => $parent->ticker,
            'direction' => 'long',
            'entry_price' => 110.00,
            'quantity' => 10,
            'entry_at' => now()->toIso8601String(),
            'parent_trade_id' => $parent->id,
            'paper' => true,
        ], withAgent($agent));

        $response->assertUnprocessable();
    });

    it('rejects exit quantity exceeding remaining parent quantity', function () {
        $agent = makeAgent(makeOwner());

        $parent = Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => '100.00000000',
            'quantity' => '10.00000000',
            'paper' => true,
        ]);

        // First partial exit: 7 shares
        Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'short',
            'entry_price' => '105.00000000',
            'quantity' => '7.00000000',
            'parent_trade_id' => $parent->id,
            'paper' => true,
        ]);

        // Second exit: 5 shares exceeds remaining 3
        $response = $this->postJson('/api/v1/trading/trades', [
            'ticker' => 'AAPL',
            'direction' => 'short',
            'entry_price' => 110.00,
            'quantity' => 5,
            'entry_at' => now()->toIso8601String(),
            'parent_trade_id' => $parent->id,
            'paper' => true,
        ], withAgent($agent));

        $response->assertUnprocessable();
    });

    it('rejects cross-agent parent_trade_id', function () {
        $owner = makeOwner();
        $agent1 = makeAgent($owner);
        $agent2 = makeAgent($owner, ['api_token' => 'amc_other_agent_token']);

        $parent = Trade::factory()->create([
            'agent_id' => $agent1->id,
            'direction' => 'long',
            'paper' => true,
        ]);

        $response = $this->postJson('/api/v1/trading/trades', [
            'ticker' => $parent->ticker,
            'direction' => 'short',
            'entry_price' => 110.00,
            'quantity' => 10,
            'entry_at' => now()->toIso8601String(),
            'parent_trade_id' => $parent->id,
            'paper' => true,
        ], withAgent($agent2));

        $response->assertUnprocessable();
    });

    it('rejects zero quantity', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/trading/trades', [
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => 100,
            'quantity' => 0,
            'entry_at' => now()->toIso8601String(),
            'paper' => true,
        ], withAgent($agent));

        $response->assertUnprocessable();
    });

    it('requires authentication', function () {
        $response = $this->postJson('/api/v1/trading/trades', [
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => 100,
            'quantity' => 10,
            'entry_at' => now()->toIso8601String(),
        ]);

        $response->assertUnauthorized();
    });
});

// ---------------------------------------------------------------------------
// PATCH /v1/trading/trades/{id} — Metadata updates only
// ---------------------------------------------------------------------------

describe('PATCH /v1/trading/trades/{id}', function () {
    it('allows updating strategy and confidence', function () {
        $agent = makeAgent(makeOwner());
        $trade = Trade::factory()->create(['agent_id' => $agent->id]);

        $response = $this->patchJson("/api/v1/trading/trades/{$trade->id}", [
            'strategy' => 'new_strategy',
            'confidence' => 0.95,
        ], withAgent($agent));

        $response->assertOk();
        $trade->refresh();
        expect($trade->strategy)->toBe('new_strategy');
        expect($trade->confidence)->toBe(0.95);
    });

    it('rejects changes to immutable fields', function () {
        $agent = makeAgent(makeOwner());
        $trade = Trade::factory()->create(['agent_id' => $agent->id]);

        $response = $this->patchJson("/api/v1/trading/trades/{$trade->id}", [
            'entry_price' => 999.99,
        ], withAgent($agent));

        $response->assertUnprocessable();
    });

    it('allows cancelling an open trade', function () {
        $agent = makeAgent(makeOwner());
        $trade = Trade::factory()->create(['agent_id' => $agent->id, 'status' => 'open']);

        $response = $this->patchJson("/api/v1/trading/trades/{$trade->id}", [
            'status' => 'cancelled',
        ], withAgent($agent));

        $response->assertOk();
        $trade->refresh();
        expect($trade->status)->toBe('cancelled');
    });

    it('rejects closing via PATCH', function () {
        $agent = makeAgent(makeOwner());
        $trade = Trade::factory()->create(['agent_id' => $agent->id, 'status' => 'open']);

        $response = $this->patchJson("/api/v1/trading/trades/{$trade->id}", [
            'status' => 'closed',
        ], withAgent($agent));

        $response->assertUnprocessable();
    });
});

// ---------------------------------------------------------------------------
// GET /v1/trading/trades — List with filters
// ---------------------------------------------------------------------------

describe('GET /v1/trading/trades', function () {
    it('returns paginated trades for the agent', function () {
        $agent = makeAgent(makeOwner());
        Trade::factory()->count(3)->create(['agent_id' => $agent->id]);

        $response = $this->getJson('/api/v1/trading/trades', withAgent($agent));

        $response->assertOk()
            ->assertJsonCount(3, 'data');
    });

    it('filters by ticker', function () {
        $agent = makeAgent(makeOwner());
        Trade::factory()->create(['agent_id' => $agent->id, 'ticker' => 'AAPL']);
        Trade::factory()->create(['agent_id' => $agent->id, 'ticker' => 'TSLA']);

        $response = $this->getJson('/api/v1/trading/trades?ticker=AAPL', withAgent($agent));

        $response->assertOk()
            ->assertJsonCount(1, 'data');
    });

    it('filters by status', function () {
        $agent = makeAgent(makeOwner());
        Trade::factory()->create(['agent_id' => $agent->id, 'status' => 'open']);
        Trade::factory()->create(['agent_id' => $agent->id, 'status' => 'closed', 'pnl' => 100]);

        $response = $this->getJson('/api/v1/trading/trades?status=open', withAgent($agent));

        $response->assertOk()
            ->assertJsonCount(1, 'data');
    });

    it('does not show other agents trades', function () {
        $owner = makeOwner();
        $agent1 = makeAgent($owner);
        $agent2 = makeAgent($owner, ['api_token' => 'amc_other']);

        Trade::factory()->create(['agent_id' => $agent1->id]);
        Trade::factory()->create(['agent_id' => $agent2->id]);

        $response = $this->getJson('/api/v1/trading/trades', withAgent($agent1));

        $response->assertOk()
            ->assertJsonCount(1, 'data');
    });
});

// ---------------------------------------------------------------------------
// DELETE /v1/trading/trades/{id}
// ---------------------------------------------------------------------------

describe('DELETE /v1/trading/trades/{id}', function () {
    it('soft deletes an open trade', function () {
        $agent = makeAgent(makeOwner());
        $trade = Trade::factory()->create(['agent_id' => $agent->id, 'status' => 'open']);

        $response = $this->deleteJson("/api/v1/trading/trades/{$trade->id}", [], withAgent($agent));

        $response->assertOk();
        expect($trade->fresh())->toBeNull(); // soft deleted
        expect(Trade::withTrashed()->find($trade->id))->not->toBeNull();
    });

    it('rejects deleting a closed trade', function () {
        $agent = makeAgent(makeOwner());
        $trade = Trade::factory()->create(['agent_id' => $agent->id, 'status' => 'closed', 'pnl' => 100]);

        $response = $this->deleteJson("/api/v1/trading/trades/{$trade->id}", [], withAgent($agent));

        $response->assertUnprocessable();
    });

    it('rejects deleting a parent trade with children', function () {
        $agent = makeAgent(makeOwner());
        $parent = Trade::factory()->create(['agent_id' => $agent->id, 'status' => 'open']);
        Trade::factory()->create([
            'agent_id' => $agent->id,
            'parent_trade_id' => $parent->id,
        ]);

        $response = $this->deleteJson("/api/v1/trading/trades/{$parent->id}", [], withAgent($agent));

        $response->assertUnprocessable();
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `php artisan test tests/Feature/TradingApiTest.php`
Expected: FAIL — routes/controller not found.

- [ ] **Step 3: Create TradingController**

Create `app/Http/Controllers/Api/TradingController.php`:

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Trade;
use Closure;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

class TradingController extends Controller
{
    public function store(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $validated = $request->validate([
            'ticker' => ['required', 'string', 'max:64'],
            'direction' => ['required', Rule::in(Trade::DIRECTIONS)],
            'entry_price' => ['required', 'numeric', 'gt:0'],
            'quantity' => ['required', 'numeric', 'gt:0'],
            'entry_at' => ['required', 'date'],
            'fees' => ['nullable', 'numeric', 'gte:0'],
            'strategy' => ['nullable', 'string', 'max:255'],
            'confidence' => ['nullable', 'numeric', 'between:0,1'],
            'paper' => ['boolean'],
            'parent_trade_id' => [
                'nullable',
                'uuid',
                function (string $attribute, mixed $value, Closure $fail) use ($agent, $request) {
                    if (! $value) {
                        return;
                    }

                    $parent = Trade::where('id', $value)
                        ->where('agent_id', $agent->id)
                        ->first();

                    if (! $parent) {
                        $fail('Parent trade not found or does not belong to this agent.');
                        return;
                    }

                    if ($parent->status !== 'open') {
                        $fail('Parent trade is not open.');
                        return;
                    }

                    if ($request->input('direction') === $parent->direction) {
                        $fail('Exit direction must oppose the parent trade direction.');
                        return;
                    }

                    if ($request->input('ticker') !== $parent->ticker) {
                        $fail('Exit ticker must match parent trade ticker.');
                        return;
                    }

                    if ((bool) $request->input('paper', true) !== $parent->paper) {
                        $fail('Exit paper flag must match parent trade.');
                        return;
                    }

                    $existingChildQty = $parent->children()->sum('quantity');
                    $newQty = $request->input('quantity');
                    $remaining = bcsub($parent->quantity, (string) $existingChildQty, 8);

                    if (bccomp((string) $newQty, $remaining, 8) > 0) {
                        $fail("Exit quantity ({$newQty}) exceeds remaining parent quantity ({$remaining}).");
                    }
                },
            ],
            'decision_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'outcome_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'metadata' => ['nullable', 'array'],
        ]);

        $validated['agent_id'] = $agent->id;
        $validated['fees'] = $validated['fees'] ?? 0;
        $validated['paper'] = $validated['paper'] ?? true;

        $trade = Trade::create($validated);

        return response()->json($trade->fresh()->load(['parentTrade', 'children']), 201);
    }

    public function index(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $query = Trade::forAgent($agent)->parentsOnly();

        if ($request->has('ticker')) {
            $query->where('ticker', $request->input('ticker'));
        }
        if ($request->has('status')) {
            $query->where('status', $request->input('status'));
        }
        if ($request->has('direction')) {
            $query->where('direction', $request->input('direction'));
        }
        if ($request->has('strategy')) {
            $query->where('strategy', $request->input('strategy'));
        }
        if ($request->has('paper')) {
            $query->where('paper', filter_var($request->input('paper'), FILTER_VALIDATE_BOOLEAN));
        }
        if ($request->has('from')) {
            $query->where('entry_at', '>=', $request->input('from'));
        }
        if ($request->has('to')) {
            $query->where('entry_at', '<=', $request->input('to'));
        }
        if ($request->has('min_pnl')) {
            $query->where('pnl', '>=', $request->input('min_pnl'));
        }
        if ($request->has('max_pnl')) {
            $query->where('pnl', '<=', $request->input('max_pnl'));
        }
        if ($request->boolean('has_decision_memory')) {
            $query->whereNotNull('decision_memory_id');
        }

        $sort = $request->input('sort', 'entry_at');
        $order = $request->input('order', 'desc');
        $allowedSorts = ['entry_at', 'pnl', 'pnl_percent', 'created_at'];
        if (in_array($sort, $allowedSorts)) {
            $query->orderBy($sort, $order === 'asc' ? 'asc' : 'desc');
        }

        $trades = $query->with(['children', 'decisionMemory', 'outcomeMemory'])
            ->cursorPaginate($request->input('limit', 50));

        return response()->json($trades);
    }

    public function show(Request $request, string $id): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $trade = Trade::forAgent($agent)
            ->with(['children', 'decisionMemory', 'outcomeMemory', 'parentTrade'])
            ->findOrFail($id);

        return response()->json($trade);
    }

    public function update(Request $request, string $id): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $trade = Trade::forAgent($agent)->findOrFail($id);

        // Reject immutable fields
        $immutable = ['ticker', 'direction', 'entry_price', 'quantity', 'fees', 'entry_at', 'parent_trade_id', 'paper'];
        foreach ($immutable as $field) {
            if ($request->has($field)) {
                return response()->json([
                    'message' => "The field '{$field}' is immutable and cannot be changed.",
                    'errors' => [$field => ["The field '{$field}' is immutable."]],
                ], 422);
            }
        }

        $validated = $request->validate([
            'strategy' => ['nullable', 'string', 'max:255'],
            'confidence' => ['nullable', 'numeric', 'between:0,1'],
            'metadata' => ['nullable', 'array'],
            'decision_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'outcome_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'status' => ['nullable', Rule::in(['cancelled'])],
        ]);

        if (isset($validated['status']) && $validated['status'] === 'cancelled' && $trade->status !== 'open') {
            return response()->json([
                'message' => 'Only open trades can be cancelled.',
                'errors' => ['status' => ['Only open trades can be cancelled.']],
            ], 422);
        }

        $trade->update($validated);

        return response()->json($trade->fresh());
    }

    public function destroy(Request $request, string $id): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $trade = Trade::forAgent($agent)->findOrFail($id);

        if ($trade->status === 'closed') {
            return response()->json([
                'message' => 'Closed trades cannot be deleted.',
                'errors' => ['id' => ['Closed trades cannot be deleted.']],
            ], 422);
        }

        if ($trade->children()->exists()) {
            return response()->json([
                'message' => 'Cannot delete a trade that has child executions.',
                'errors' => ['id' => ['Cannot delete a trade that has child executions.']],
            ], 422);
        }

        $trade->delete();

        return response()->json(['message' => 'Trade deleted.']);
    }
}
```

- [ ] **Step 4: Add trading routes to `routes/api.php`**

Add inside the authenticated middleware group (after the Arena routes, before the closing `});`):

```php
        // Trading
        Route::post('trading/trades', [\App\Http\Controllers\Api\TradingController::class, 'store']);
        Route::get('trading/trades', [\App\Http\Controllers\Api\TradingController::class, 'index']);
        Route::get('trading/trades/{id}', [\App\Http\Controllers\Api\TradingController::class, 'show']);
        Route::patch('trading/trades/{id}', [\App\Http\Controllers\Api\TradingController::class, 'update']);
        Route::delete('trading/trades/{id}', [\App\Http\Controllers\Api\TradingController::class, 'destroy']);
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradingApiTest.php`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/Http/Controllers/Api/TradingController.php tests/Feature/TradingApiTest.php routes/api.php
git commit -m "feat(trading): add trade CRUD endpoints with validation"
```

---

## Task 6: Positions + Stats Endpoints

**Files:**
- Create: `app/Http/Controllers/Api/TradingPositionController.php`
- Create: `app/Http/Controllers/Api/TradingStatsController.php`
- Modify: `routes/api.php`
- Modify: `tests/Feature/TradingApiTest.php`

- [ ] **Step 1: Add position and stats tests to `TradingApiTest.php`**

Append to the end of `tests/Feature/TradingApiTest.php`:

```php
// ---------------------------------------------------------------------------
// GET /v1/trading/positions
// ---------------------------------------------------------------------------

describe('GET /v1/trading/positions', function () {
    it('returns current open positions', function () {
        $agent = makeAgent(makeOwner());

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => '100.00000000',
            'quantity' => '10.00000000',
            'status' => 'open',
            'paper' => true,
        ]);

        // Trigger position recalculation
        app(\App\Services\TradingService::class)->recalculatePosition($agent, 'AAPL', true);

        $response = $this->getJson('/api/v1/trading/positions', withAgent($agent));

        $response->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonFragment(['ticker' => 'AAPL']);
    });

    it('filters by paper flag', function () {
        $agent = makeAgent(makeOwner());
        $service = app(\App\Services\TradingService::class);

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'status' => 'open',
            'paper' => true,
        ]);
        $service->recalculatePosition($agent, 'AAPL', true);

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'TSLA',
            'status' => 'open',
            'paper' => false,
        ]);
        $service->recalculatePosition($agent, 'TSLA', false);

        $response = $this->getJson('/api/v1/trading/positions?paper=true', withAgent($agent));

        $response->assertOk()
            ->assertJsonCount(1, 'data');
    });
});

// ---------------------------------------------------------------------------
// GET /v1/trading/stats
// ---------------------------------------------------------------------------

describe('GET /v1/trading/stats', function () {
    it('returns aggregate stats for the agent', function () {
        $agent = makeAgent(makeOwner());

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'status' => 'closed',
            'pnl' => '100.00000000',
            'pnl_percent' => '10.0000',
            'entry_at' => now(),
            'paper' => true,
        ]);

        app(\App\Services\TradingService::class)->recalculateStats($agent, true);

        $response = $this->getJson('/api/v1/trading/stats?paper=true', withAgent($agent));

        $response->assertOk()
            ->assertJsonFragment([
                'total_trades' => 1,
                'win_count' => 1,
            ]);
    });
});

// ---------------------------------------------------------------------------
// GET /v1/trading/stats/by-ticker
// ---------------------------------------------------------------------------

describe('GET /v1/trading/stats/by-ticker', function () {
    it('returns per-ticker breakdown', function () {
        $agent = makeAgent(makeOwner());

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'status' => 'closed',
            'pnl' => '100.00000000',
            'pnl_percent' => '10.0000',
            'entry_at' => now(),
            'paper' => true,
        ]);

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'TSLA',
            'status' => 'closed',
            'pnl' => '-50.00000000',
            'pnl_percent' => '-5.0000',
            'entry_at' => now(),
            'paper' => true,
        ]);

        $response = $this->getJson('/api/v1/trading/stats/by-ticker?paper=true', withAgent($agent));

        $response->assertOk()
            ->assertJsonCount(2, 'data');
    });
});

// ---------------------------------------------------------------------------
// GET /v1/trading/stats/equity-curve
// ---------------------------------------------------------------------------

describe('GET /v1/trading/stats/equity-curve', function () {
    it('returns cumulative PnL time series', function () {
        $agent = makeAgent(makeOwner());

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'status' => 'closed',
            'pnl' => '100.00000000',
            'entry_at' => '2026-03-01',
            'exit_at' => '2026-03-01',
            'paper' => true,
        ]);

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'status' => 'closed',
            'pnl' => '50.00000000',
            'entry_at' => '2026-03-02',
            'exit_at' => '2026-03-02',
            'paper' => true,
        ]);

        $response = $this->getJson('/api/v1/trading/stats/equity-curve?paper=true', withAgent($agent));

        $response->assertOk()
            ->assertJsonCount(2, 'data');

        $data = $response->json('data');
        // Cumulative: first = 100, second = 150
        expect((float) $data[1]['cumulative_pnl'])->toBe(150.0);
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `php artisan test tests/Feature/TradingApiTest.php --filter="positions|stats|equity"`
Expected: FAIL — controllers/routes not found.

- [ ] **Step 3: Create TradingPositionController**

Create `app/Http/Controllers/Api/TradingPositionController.php`:

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Position;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class TradingPositionController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $query = Position::where('agent_id', $agent->id);

        if ($request->has('paper')) {
            $query->where('paper', filter_var($request->input('paper'), FILTER_VALIDATE_BOOLEAN));
        }

        $positions = $query->orderBy('ticker')->get();

        return response()->json(['data' => $positions]);
    }

    public function show(Request $request, string $ticker): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $paper = filter_var($request->input('paper', 'true'), FILTER_VALIDATE_BOOLEAN);

        $position = Position::where('agent_id', $agent->id)
            ->where('ticker', $ticker)
            ->where('paper', $paper)
            ->firstOrFail();

        return response()->json($position);
    }
}
```

- [ ] **Step 4: Create TradingStatsController**

Create `app/Http/Controllers/Api/TradingStatsController.php`:

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Trade;
use App\Models\TradingStats;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class TradingStatsController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $paper = filter_var($request->input('paper', 'true'), FILTER_VALIDATE_BOOLEAN);

        $stats = TradingStats::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->first();

        if (! $stats) {
            return response()->json([
                'paper' => $paper,
                'total_trades' => 0,
                'win_count' => 0,
                'loss_count' => 0,
                'win_rate' => null,
                'profit_factor' => null,
                'total_pnl' => 0,
                'avg_pnl_percent' => null,
                'best_trade_pnl' => null,
                'worst_trade_pnl' => null,
                'sharpe_ratio' => null,
                'current_streak' => 0,
            ]);
        }

        return response()->json($stats);
    }

    public function byTicker(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $paper = filter_var($request->input('paper', 'true'), FILTER_VALIDATE_BOOLEAN);

        $data = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->select('ticker')
            ->selectRaw('COUNT(*) as total_trades')
            ->selectRaw('SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as win_count')
            ->selectRaw('ROUND(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_rate')
            ->selectRaw('SUM(pnl) as total_pnl')
            ->selectRaw('CASE WHEN SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) > 0 THEN ROUND(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) / SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END), 4) ELSE NULL END as profit_factor')
            ->groupBy('ticker')
            ->orderByRaw('SUM(pnl) DESC')
            ->get();

        return response()->json(['data' => $data]);
    }

    public function byStrategy(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $paper = filter_var($request->input('paper', 'true'), FILTER_VALIDATE_BOOLEAN);

        $data = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->whereNotNull('strategy')
            ->select('strategy')
            ->selectRaw('COUNT(*) as total_trades')
            ->selectRaw('SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as win_count')
            ->selectRaw('ROUND(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_rate')
            ->selectRaw('SUM(pnl) as total_pnl')
            ->selectRaw('CASE WHEN SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) > 0 THEN ROUND(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) / SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END), 4) ELSE NULL END as profit_factor')
            ->groupBy('strategy')
            ->orderByRaw('SUM(pnl) DESC')
            ->get();

        return response()->json(['data' => $data]);
    }

    public function equityCurve(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $paper = filter_var($request->input('paper', 'true'), FILTER_VALIDATE_BOOLEAN);

        $dailyPnl = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->selectRaw("DATE(exit_at) as date")
            ->selectRaw('SUM(pnl) as daily_pnl')
            ->groupByRaw('DATE(exit_at)')
            ->orderByRaw('DATE(exit_at)')
            ->get();

        $cumulative = '0';
        $data = $dailyPnl->map(function ($row) use (&$cumulative) {
            $cumulative = bcadd($cumulative, (string) $row->daily_pnl, 8);
            return [
                'date' => $row->date,
                'cumulative_pnl' => (float) $cumulative,
            ];
        });

        return response()->json(['data' => $data->values()]);
    }
}
```

- [ ] **Step 5: Add routes to `routes/api.php`**

Add inside the authenticated middleware group, after the trading/trades routes:

```php
        Route::get('trading/positions', [\App\Http\Controllers\Api\TradingPositionController::class, 'index']);
        Route::get('trading/positions/{ticker}', [\App\Http\Controllers\Api\TradingPositionController::class, 'show']);
        Route::get('trading/stats', [\App\Http\Controllers\Api\TradingStatsController::class, 'index']);
        Route::get('trading/stats/by-ticker', [\App\Http\Controllers\Api\TradingStatsController::class, 'byTicker']);
        Route::get('trading/stats/by-strategy', [\App\Http\Controllers\Api\TradingStatsController::class, 'byStrategy']);
        Route::get('trading/stats/equity-curve', [\App\Http\Controllers\Api\TradingStatsController::class, 'equityCurve']);
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradingApiTest.php`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/Http/Controllers/Api/TradingPositionController.php app/Http/Controllers/Api/TradingStatsController.php routes/api.php tests/Feature/TradingApiTest.php
git commit -m "feat(trading): add positions, stats, equity-curve endpoints"
```

---

## Task 7: Public Leaderboard + Agent Trading Profile

**Files:**
- Create: `app/Http/Controllers/Api/TradingLeaderboardController.php`
- Modify: `routes/api.php`
- Modify: `tests/Feature/TradingApiTest.php`

- [ ] **Step 1: Add leaderboard tests to `TradingApiTest.php`**

Append to the end of `tests/Feature/TradingApiTest.php`:

```php
// ---------------------------------------------------------------------------
// GET /v1/trading/leaderboard — Public
// ---------------------------------------------------------------------------

describe('GET /v1/trading/leaderboard', function () {
    it('returns agents ranked by total PnL', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner, ['is_listed' => true]);

        \App\Models\TradingStats::create([
            'agent_id' => $agent->id,
            'paper' => false,
            'total_trades' => 10,
            'win_count' => 7,
            'loss_count' => 3,
            'win_rate' => 70.0,
            'total_pnl' => 5000,
        ]);

        $response = $this->getJson('/api/v1/trading/leaderboard');

        $response->assertOk()
            ->assertJsonFragment(['agent_name' => $agent->name]);
    });

    it('defaults to live trades (paper=false)', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner, ['is_listed' => true]);

        // Paper stats only
        \App\Models\TradingStats::create([
            'agent_id' => $agent->id,
            'paper' => true,
            'total_trades' => 10,
            'total_pnl' => 5000,
        ]);

        $response = $this->getJson('/api/v1/trading/leaderboard');

        $response->assertOk()
            ->assertJsonCount(0, 'entries');
    });

    it('shows paper leaderboard when requested', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner, ['is_listed' => true]);

        \App\Models\TradingStats::create([
            'agent_id' => $agent->id,
            'paper' => true,
            'total_trades' => 10,
            'total_pnl' => 5000,
        ]);

        $response = $this->getJson('/api/v1/trading/leaderboard?paper=true');

        $response->assertOk()
            ->assertJsonCount(1, 'entries');
    });

    it('does not require authentication', function () {
        $response = $this->getJson('/api/v1/trading/leaderboard');

        $response->assertOk();
    });
});

// ---------------------------------------------------------------------------
// GET /v1/trading/agents/{agentId}/profile — Public
// ---------------------------------------------------------------------------

describe('GET /v1/trading/agents/{agentId}/profile', function () {
    it('returns public trading profile', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner, ['is_listed' => true]);

        \App\Models\TradingStats::create([
            'agent_id' => $agent->id,
            'paper' => true,
            'total_trades' => 5,
            'total_pnl' => 1000,
        ]);

        $response = $this->getJson("/api/v1/trading/agents/{$agent->id}/profile");

        $response->assertOk()
            ->assertJsonFragment(['agent_name' => $agent->name]);
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `php artisan test tests/Feature/TradingApiTest.php --filter="leaderboard|profile"`
Expected: FAIL — routes/controller not found.

- [ ] **Step 3: Create TradingLeaderboardController**

Create `app/Http/Controllers/Api/TradingLeaderboardController.php`:

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\Trade;
use App\Models\TradingStats;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;

class TradingLeaderboardController extends Controller
{
    public function leaderboard(Request $request): JsonResponse
    {
        $paper = filter_var($request->input('paper', 'false'), FILTER_VALIDATE_BOOLEAN);
        $sort = $request->input('sort', 'total_pnl');
        $allowedSorts = ['total_pnl', 'win_rate', 'sharpe_ratio', 'profit_factor'];
        $sort = in_array($sort, $allowedSorts) ? $sort : 'total_pnl';

        $cacheKey = "trading_leaderboard:{$sort}:" . ($paper ? 'paper' : 'live');

        $entries = Cache::remember($cacheKey, 300, function () use ($paper, $sort) {
            return TradingStats::where('paper', $paper)
                ->where('total_trades', '>', 0)
                ->whereHas('agent', fn ($q) => $q->where('is_listed', true))
                ->orderByDesc($sort)
                ->limit(25)
                ->get()
                ->map(fn (TradingStats $stats) => [
                    'agent_id' => $stats->agent_id,
                    'agent_name' => $stats->agent->name,
                    'total_trades' => $stats->total_trades,
                    'win_rate' => $stats->win_rate,
                    'total_pnl' => $stats->total_pnl,
                    'profit_factor' => $stats->profit_factor,
                    'sharpe_ratio' => $stats->sharpe_ratio,
                    'current_streak' => $stats->current_streak,
                ])
                ->toArray();
        });

        return response()->json([
            'type' => 'trading',
            'paper' => $paper,
            'sort' => $sort,
            'entries' => $entries,
        ]);
    }

    public function agentProfile(Request $request, string $agentId): JsonResponse
    {
        $agent = Agent::where('id', $agentId)->where('is_listed', true)->firstOrFail();

        $stats = TradingStats::where('agent_id', $agent->id)->get()->keyBy(fn ($s) => $s->paper ? 'paper' : 'live');

        return response()->json([
            'agent_id' => $agent->id,
            'agent_name' => $agent->name,
            'paper_stats' => $stats->get('paper'),
            'live_stats' => $stats->get('live'),
        ]);
    }

    public function agentTrades(Request $request, string $agentId): JsonResponse
    {
        $agent = Agent::where('id', $agentId)->where('is_listed', true)->firstOrFail();

        $paper = filter_var($request->input('paper', 'true'), FILTER_VALIDATE_BOOLEAN);

        $trades = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->whereNull('parent_trade_id')
            ->where('status', 'closed')
            ->with(['decisionMemory' => fn ($q) => $q->where('visibility', 'public')])
            ->orderByDesc('exit_at')
            ->cursorPaginate($request->input('limit', 50));

        return response()->json($trades);
    }
}
```

- [ ] **Step 4: Add public routes to `routes/api.php`**

Add inside the public routes section (before the authenticated middleware group), after the commons/poll route:

```php
    // Trading — public
    Route::get('trading/leaderboard', [\App\Http\Controllers\Api\TradingLeaderboardController::class, 'leaderboard']);
    Route::get('trading/agents/{agentId}/profile', [\App\Http\Controllers\Api\TradingLeaderboardController::class, 'agentProfile'])
        ->where('agentId', '[0-9a-f\-]{36}');
    Route::get('trading/agents/{agentId}/trades', [\App\Http\Controllers\Api\TradingLeaderboardController::class, 'agentTrades'])
        ->where('agentId', '[0-9a-f\-]{36}');
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `php artisan test tests/Feature/TradingApiTest.php`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/Http/Controllers/Api/TradingLeaderboardController.php routes/api.php tests/Feature/TradingApiTest.php
git commit -m "feat(trading): add public leaderboard and agent trading profiles"
```

---

## Task 8: Trading Achievements

**Files:**
- Modify: `app/Services/AchievementService.php`
- Modify: `tests/Feature/TradingApiTest.php`

- [ ] **Step 1: Add trading achievement test**

Append to `tests/Feature/TradingApiTest.php`:

```php
// ---------------------------------------------------------------------------
// Achievements
// ---------------------------------------------------------------------------

describe('Trading Achievements', function () {
    it('awards first_trade achievement', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/trading/trades', [
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => 100,
            'quantity' => 10,
            'entry_at' => now()->toIso8601String(),
            'paper' => true,
        ], withAgent($agent));

        $this->assertDatabaseHas('achievements', [
            'agent_id' => $agent->id,
            'slug' => 'first_trade',
        ]);
    });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php artisan test tests/Feature/TradingApiTest.php --filter="first_trade"`
Expected: FAIL — no `first_trade` achievement definition exists yet.

- [ ] **Step 3: Add trading achievements to AchievementService**

In `app/Services/AchievementService.php`, add these entries to the `DEFINITIONS` constant:

```php
'first_trade' => [
    'triggers' => ['trade'],
    'checker' => 'checkFirstTrade',
],
'first_win' => [
    'triggers' => ['trade'],
    'checker' => 'checkFirstWin',
],
'streak_5' => [
    'triggers' => ['trade'],
    'checker' => 'checkStreak5',
],
'century_club' => [
    'triggers' => ['trade'],
    'checker' => 'checkCenturyClub',
],
'sharp_shooter' => [
    'triggers' => ['trade'],
    'checker' => 'checkSharpShooter',
],
```

Then add these checker methods to the class:

```php
private function checkFirstTrade(Agent $agent): bool
{
    return \App\Models\Trade::where('agent_id', $agent->id)->count() >= 1;
}

private function checkFirstWin(Agent $agent): bool
{
    return \App\Models\Trade::where('agent_id', $agent->id)
        ->where('status', 'closed')
        ->whereNull('parent_trade_id')
        ->where('pnl', '>', 0)
        ->exists();
}

private function checkStreak5(Agent $agent): bool
{
    $stats = \App\Models\TradingStats::where('agent_id', $agent->id)->first();
    return $stats && $stats->current_streak >= 5;
}

private function checkCenturyClub(Agent $agent): bool
{
    return \App\Models\Trade::where('agent_id', $agent->id)
        ->whereNull('parent_trade_id')
        ->count() >= 100;
}

private function checkSharpShooter(Agent $agent): bool
{
    $stats = \App\Models\TradingStats::where('agent_id', $agent->id)->first();
    return $stats && $stats->total_trades >= 20 && (float) $stats->win_rate > 70.0;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `php artisan test tests/Feature/TradingApiTest.php --filter="first_trade"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/Services/AchievementService.php tests/Feature/TradingApiTest.php
git commit -m "feat(trading): add trading achievements"
```

---

## Task 9: Run Full Test Suite

- [ ] **Step 1: Run all trading tests**

Run: `php artisan test tests/Feature/TradingApiTest.php tests/Unit/TradingServiceTest.php -v`
Expected: All tests PASS.

- [ ] **Step 2: Run the existing test suite to check for regressions**

Run: `php artisan test`
Expected: All existing tests still PASS. No regressions.

- [ ] **Step 3: Run style checks**

Run: `./vendor/bin/pint`
Expected: Code formatted, no issues.

- [ ] **Step 4: Commit any formatting fixes**

```bash
git add -A
git commit -m "style: format trading vertical code"
```

---

## Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Database migrations (3 tables) | Migration runs |
| 2 | Models + Factory + Agent relationships | — |
| 3 | TradingService (PnL, stats, positions) | 6 unit tests |
| 4 | TradeObserver (event orchestration) | — |
| 5 | TradingController (trade CRUD) | ~12 feature tests |
| 6 | Positions + Stats endpoints | ~5 feature tests |
| 7 | Public leaderboard + profiles | ~5 feature tests |
| 8 | Trading achievements | 1 feature test |
| 9 | Full suite run + formatting | Regression check |
