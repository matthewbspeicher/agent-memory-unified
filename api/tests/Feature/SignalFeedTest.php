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
// GET /v1/trading/signals — Copy-trading signal feed
// ---------------------------------------------------------------------------

it('lists recent signals from broadcasting agents', function () {
    $agent = makeAgent(makeOwner(), [
        'is_listed' => true,
        'broadcasts_signals' => true,
    ]);

    $trade = Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '185.50000000',
        'quantity' => '100.00000000',
        'status' => 'closed',
        'paper' => false,
        'pnl' => '250.00000000',
        'pnl_percent' => '1.3500',
    ]);

    $response = $this->getJson('/api/v1/trading/signals', withAgent($agent));

    $response->assertOk()
        ->assertJsonCount(1, 'data')
        ->assertJsonPath('data.0.ticker', 'AAPL')
        ->assertJsonPath('data.0.agent_name', $agent->name);
});

it('excludes paper trades from signal feed', function () {
    $agent = makeAgent(makeOwner(), [
        'is_listed' => true,
        'broadcasts_signals' => true,
    ]);

    Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'TSLA',
        'direction' => 'long',
        'status' => 'closed',
        'paper' => true,
    ]);

    $response = $this->getJson('/api/v1/trading/signals', withAgent($agent));

    $response->assertOk()
        ->assertJsonCount(0, 'data');
});

it('excludes non-broadcasting agents', function () {
    $agent = makeAgent(makeOwner(), [
        'is_listed' => true,
        'broadcasts_signals' => false,
    ]);

    Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'MSFT',
        'direction' => 'short',
        'status' => 'closed',
        'paper' => false,
    ]);

    $response = $this->getJson('/api/v1/trading/signals', withAgent($agent));

    $response->assertOk()
        ->assertJsonCount(0, 'data');
});

it('allows filtering signals by ticker', function () {
    $agent = makeAgent(makeOwner(), [
        'is_listed' => true,
        'broadcasts_signals' => true,
    ]);

    Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'status' => 'closed',
        'paper' => false,
    ]);

    Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'TSLA',
        'direction' => 'long',
        'status' => 'closed',
        'paper' => false,
    ]);

    $response = $this->getJson('/api/v1/trading/signals?ticker=AAPL', withAgent($agent));

    $response->assertOk()
        ->assertJsonCount(1, 'data')
        ->assertJsonPath('data.0.ticker', 'AAPL');
});

it('allows agent to enable signal broadcasting', function () {
    $agent = makeAgent(makeOwner(), [
        'broadcasts_signals' => false,
    ]);

    $response = $this->patchJson('/api/v1/agents/me', [
        'broadcasts_signals' => true,
    ], withAgent($agent));

    $response->assertOk();

    $agent->refresh();
    expect($agent->broadcasts_signals)->toBeTrue();
});
