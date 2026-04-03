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

    $this->agent = makeAgent(makeOwner());
});

it('accepts tags when creating a trade', function () {
    $response = $this->postJson('/api/v1/trading/trades', [
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '150.00',
        'quantity' => '10',
        'entry_at' => now()->toIso8601String(),
        'tags' => ['earnings-play', 'momentum'],
    ], withAgent($this->agent));

    $response->assertCreated();
    expect($response->json('tags'))->toBe(['earnings-play', 'momentum']);
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

    $response = $this->getJson('/api/v1/trading/trades?tag=momentum', withAgent($this->agent));

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
    ], withAgent($this->agent));

    $response->assertOk();
    expect($response->json('tags'))->toBe(['new-tag', 'updated']);
});

it('validates tags are strings', function () {
    $response = $this->postJson('/api/v1/trading/trades', [
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '150.00',
        'quantity' => '10',
        'entry_at' => now()->toIso8601String(),
        'tags' => [123, true],
    ], withAgent($this->agent));

    $response->assertUnprocessable();
});
