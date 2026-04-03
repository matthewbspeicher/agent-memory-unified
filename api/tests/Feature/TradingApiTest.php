<?php

use App\Models\Trade;
use App\Models\TradingStats;
use App\Services\EmbeddingService;
use App\Services\TradingService;
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

    it('remains open on partial exit', function () {
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
            'quantity' => 4,
            'entry_at' => now()->toIso8601String(),
            'parent_trade_id' => $parent->id,
            'paper' => true,
        ], withAgent($agent));

        $response->assertCreated();

        $parent->refresh();
        expect($parent->status)->toBe('open');
        expect((float) $parent->pnl)->toBeGreaterThan(0);
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

        Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'short',
            'entry_price' => '105.00000000',
            'quantity' => '7.00000000',
            'parent_trade_id' => $parent->id,
            'paper' => true,
        ]);

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
        expect(Trade::find($trade->id))->toBeNull();
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

        app(TradingService::class)->recalculatePosition($agent, 'AAPL', true);

        $response = $this->getJson('/api/v1/trading/positions', withAgent($agent));

        $response->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonFragment(['ticker' => 'AAPL']);
    });

    it('filters by paper flag', function () {
        $agent = makeAgent(makeOwner());
        $service = app(TradingService::class);

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

        app(TradingService::class)->recalculateStats($agent, true);

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
        expect((float) $data[1]['cumulative_pnl'])->toBe(150.0);
    });
});

// ---------------------------------------------------------------------------
// GET /v1/trading/leaderboard — Public
// ---------------------------------------------------------------------------

describe('GET /v1/trading/leaderboard', function () {
    it('returns agents ranked by total PnL', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner, ['is_listed' => true]);

        TradingStats::create([
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

        TradingStats::create([
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

        TradingStats::create([
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

        TradingStats::create([
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
            'achievement_slug' => 'first_trade',
        ]);
    });
});
