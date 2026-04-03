<?php

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
// POST /v1/trading/replay
// ---------------------------------------------------------------------------

it('replays historical trades with original exit prices', function () {
    $agent = makeAgent(makeOwner());

    // Trade 1: long AAPL, entry=100, exit=120, qty=10, fees=5 → pnl = (120-100)*10 - 5 = 195
    Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => 100,
        'exit_price' => 120,
        'quantity' => 10,
        'fees' => 5,
        'pnl' => 195,
        'status' => 'closed',
        'paper' => false,
        'parent_trade_id' => null,
        'entry_at' => '2026-01-01T10:00:00Z',
        'exit_at' => '2026-01-02T10:00:00Z',
    ]);

    // Trade 2: short BTC, entry=50000, exit=48000, qty=1, fees=10 → pnl = (50000-48000)*1 - 10 = 1990
    Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'BTC',
        'direction' => 'short',
        'entry_price' => 50000,
        'exit_price' => 48000,
        'quantity' => 1,
        'fees' => 10,
        'pnl' => 1990,
        'status' => 'closed',
        'paper' => false,
        'parent_trade_id' => null,
        'entry_at' => '2026-01-03T10:00:00Z',
        'exit_at' => '2026-01-04T10:00:00Z',
    ]);

    $response = $this->postJson('/api/v1/trading/replay', [
        'paper' => false,
    ], withAgent($agent));

    $response->assertOk();

    $data = $response->json('data');
    expect($data['total_trades'])->toBe(2);
    expect($data['wins'])->toBe(2);
    expect($data['losses'])->toBe(0);
    expect($data['win_rate'])->toBe(100.0);
    expect($data['total_pnl'])->toBe(2185.0);
});

it('replays with alternative exit prices', function () {
    $agent = makeAgent(makeOwner());

    // Long AAPL entry=100, exit=120, but override exit to 90 → pnl = (90-100)*10 - 0 = -100
    Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => 100,
        'exit_price' => 120,
        'quantity' => 10,
        'fees' => 0,
        'pnl' => 200,
        'status' => 'closed',
        'paper' => false,
        'parent_trade_id' => null,
        'entry_at' => '2026-01-01T10:00:00Z',
        'exit_at' => '2026-01-02T10:00:00Z',
    ]);

    $response = $this->postJson('/api/v1/trading/replay', [
        'paper' => false,
        'exit_overrides' => ['AAPL' => 90],
    ], withAgent($agent));

    $response->assertOk();

    $data = $response->json('data');
    expect($data['total_pnl'])->toBe(-100.0);
    expect($data['wins'])->toBe(0);
    expect($data['losses'])->toBe(1);
});

it('replays with exit_offset percentage', function () {
    $agent = makeAgent(makeOwner());

    // Long AAPL entry=100, exit=110, offset=-5% → simulated exit = 110 * 0.95 = 104.5
    // pnl = (104.5-100)*10 - 0 = 45
    Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => 100,
        'exit_price' => 110,
        'quantity' => 10,
        'fees' => 0,
        'pnl' => 100,
        'status' => 'closed',
        'paper' => false,
        'parent_trade_id' => null,
        'entry_at' => '2026-01-01T10:00:00Z',
        'exit_at' => '2026-01-02T10:00:00Z',
    ]);

    $response = $this->postJson('/api/v1/trading/replay', [
        'paper' => false,
        'exit_offset_pct' => -5,
    ], withAgent($agent));

    $response->assertOk();

    $data = $response->json('data');
    expect($data['total_pnl'])->toBe(45.0);
    expect($data['trades'][0]['exit_price_used'])->toBe(104.5);
});
