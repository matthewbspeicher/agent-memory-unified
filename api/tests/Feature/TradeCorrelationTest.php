<?php

use App\Models\Agent;
use App\Models\Trade;

beforeEach(function () {
    $this->agent = Agent::factory()->create();
    $this->headers = ['Authorization' => "Bearer {$this->agent->api_token}"];
});

it('returns correlation matrix between tickers', function () {
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
    expect((float) $data['AAPL']['TSLA'])->toBeGreaterThan(0.9);
});

it('returns empty data with insufficient trades', function () {
    $response = $this->getJson('/api/v1/trading/stats/correlations?paper=false', $this->headers);

    $response->assertOk();
    expect($response->json('data'))->toBeEmpty();
});

it('returns null for ticker pairs without overlapping exit dates', function () {
    foreach (range(1, 3) as $i) {
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
            'exit_at' => now()->subDays(20 - $i),
        ]);
    }

    $response = $this->getJson('/api/v1/trading/stats/correlations?paper=false', $this->headers);

    $response->assertOk();
    expect($response->json('data.AAPL.TSLA'))->toBeNull();
    expect($response->json('data.TSLA.AAPL'))->toBeNull();
});
