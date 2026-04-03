<?php

use App\Models\Position;
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
// GET /v1/trading/risk — Position risk metrics
// ---------------------------------------------------------------------------

it('returns risk metrics for open positions', function () {
    $agent = makeAgent(makeOwner());

    Position::create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'paper' => true,
        'quantity' => '10.00000000',
        'avg_entry_price' => '150.00000000',
    ]);

    $response = $this->getJson('/api/v1/trading/risk?paper=true&market_prices[AAPL]=160', withAgent($agent));

    $response->assertOk()
        ->assertJsonPath('data.0.ticker', 'AAPL')
        ->assertJsonPath('data.0.unrealized_pnl', 100.0)
        ->assertJsonPath('data.0.exposure', 1600.0)
        ->assertJsonPath('data.0.exposure_pct', null);
});

it('calculates exposure percentage when portfolio value is declared', function () {
    $agent = makeAgent(makeOwner());

    Position::create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'paper' => true,
        'quantity' => '10.00000000',
        'avg_entry_price' => '150.00000000',
        'declared_portfolio_value' => '10000.00000000',
    ]);

    $response = $this->getJson('/api/v1/trading/risk?paper=true&market_prices[AAPL]=150', withAgent($agent));

    $response->assertOk()
        ->assertJsonPath('data.0.exposure_pct', 15.0);
});

// ---------------------------------------------------------------------------
// GET /v1/trading/risk/drawdown — Max drawdown
// ---------------------------------------------------------------------------

it('returns max drawdown from closed trades', function () {
    $agent = makeAgent(makeOwner());

    // Three closed parent trades with known PnL values
    // Cumulative: 50, 20 (50-30), 0 (20-20)
    // Peak = 50, trough = 0, drawdown = 0 - 50 = -50
    Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'status' => 'closed',
        'paper' => true,
        'pnl' => '50.00000000',
        'exit_at' => '2026-03-01T10:00:00Z',
        'exit_price' => '110.00000000',
    ]);

    Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'status' => 'closed',
        'paper' => true,
        'pnl' => '-30.00000000',
        'exit_at' => '2026-03-02T10:00:00Z',
        'exit_price' => '97.00000000',
    ]);

    Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'status' => 'closed',
        'paper' => true,
        'pnl' => '-20.00000000',
        'exit_at' => '2026-03-03T10:00:00Z',
        'exit_price' => '80.00000000',
    ]);

    $response = $this->getJson('/api/v1/trading/risk/drawdown?paper=true', withAgent($agent));

    $response->assertOk()
        ->assertJsonPath('data.max_drawdown', -50.0)
        ->assertJsonPath('data.peak', 50.0)
        ->assertJsonPath('data.trough', 0.0);
});
