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

    $owner = makeOwner();
    $this->agent = makeAgent($owner);
    $this->headers = withAgent($this->agent);
});

it('exports trades as JSON', function () {
    Trade::factory()->count(3)->create([
        'agent_id' => $this->agent->id,
        'paper' => false,
        'status' => 'closed',
        'exit_price' => 200,
        'exit_at' => now(),
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
        'exit_price' => 200,
        'exit_at' => now(),
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

it('includes trades later on the to date when using a date-only filter', function () {
    $includedAt = now()->subDay()->startOfDay()->addHours(15);

    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'paper' => false,
        'entry_at' => $includedAt,
    ]);

    Trade::factory()->create([
        'agent_id' => $this->agent->id,
        'paper' => false,
        'entry_at' => $includedAt->copy()->addDay(),
    ]);

    $to = $includedAt->toDateString();
    $response = $this->getJson("/api/v1/trading/export?format=json&paper=false&to={$to}", $this->headers);

    $response->assertOk();
    expect($response->json('data'))->toHaveCount(1);
});
