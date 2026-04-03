<?php

use App\Models\Position;
use App\Models\TradingStats;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        $mock->shouldReceive('embedBatch')->andReturn([array_fill(0, 1536, 0.1)]);
    });
});

describe('GET /v1/trading/portfolio', function () {
    it('aggregates positions across agents owned by the same user', function () {
        $owner = makeOwner();
        $agent1 = makeAgent($owner, ['name' => 'Agent Alpha']);
        $agent2 = makeAgent($owner, ['name' => 'Agent Beta']);

        Position::create([
            'agent_id' => $agent1->id,
            'ticker' => 'AAPL',
            'paper' => false,
            'quantity' => '10.00000000',
            'avg_entry_price' => '150.00000000',
        ]);

        Position::create([
            'agent_id' => $agent2->id,
            'ticker' => 'AAPL',
            'paper' => false,
            'quantity' => '5.00000000',
            'avg_entry_price' => '160.00000000',
        ]);

        Position::create([
            'agent_id' => $agent1->id,
            'ticker' => 'TSLA',
            'paper' => false,
            'quantity' => '20.00000000',
            'avg_entry_price' => '250.00000000',
        ]);

        $response = $this->getJson('/api/v1/trading/portfolio?paper=false', withAgent($agent1));

        $response->assertOk();

        $positions = $response->json('data.positions');
        expect($positions)->toHaveCount(2);

        $aapl = collect($positions)->firstWhere('ticker', 'AAPL');
        expect($aapl['total_quantity'])->toBe(15.0);
        expect($aapl['agent_count'])->toBe(2);
        // Weighted avg: (10*150 + 5*160) / 15 = 2300/15 ≈ 153.33333333
        expect($aapl['avg_entry_price'])->toBeGreaterThan(153.0);
        expect($aapl['avg_entry_price'])->toBeLessThan(154.0);
    });

    it('aggregates stats across agents owned by the same user', function () {
        $owner = makeOwner();
        $agent1 = makeAgent($owner, ['name' => 'Agent Alpha']);
        $agent2 = makeAgent($owner, ['name' => 'Agent Beta']);

        TradingStats::create([
            'agent_id' => $agent1->id,
            'paper' => false,
            'total_trades' => 10,
            'win_count' => 7,
            'loss_count' => 3,
            'total_pnl' => '500.00000000',
            'win_rate' => '0.70',
        ]);

        TradingStats::create([
            'agent_id' => $agent2->id,
            'paper' => false,
            'total_trades' => 5,
            'win_count' => 3,
            'loss_count' => 2,
            'total_pnl' => '200.00000000',
            'win_rate' => '0.60',
        ]);

        $response = $this->getJson('/api/v1/trading/portfolio?paper=false', withAgent($agent1));

        $response->assertOk();

        $stats = $response->json('data.aggregate_stats');
        expect($stats['total_trades'])->toBe(15);
        expect($stats['win_count'])->toBe(10);
        expect($stats['total_pnl'])->toBe(700.0);
        expect($stats['agent_count'])->toBe(2);
    });

    it('does not include agents from other owners', function () {
        $owner1 = makeOwner(['api_token' => 'owner_1_token']);
        $agent1 = makeAgent($owner1, ['name' => 'My Agent']);

        $owner2 = makeOwner(['api_token' => 'owner_2_token', 'email' => 'other@example.com']);
        $otherAgent = makeAgent($owner2, ['name' => 'Other Agent']);

        Position::create([
            'agent_id' => $agent1->id,
            'ticker' => 'AAPL',
            'paper' => false,
            'quantity' => '10.00000000',
            'avg_entry_price' => '150.00000000',
        ]);

        Position::create([
            'agent_id' => $otherAgent->id,
            'ticker' => 'GOOG',
            'paper' => false,
            'quantity' => '5.00000000',
            'avg_entry_price' => '140.00000000',
        ]);

        $response = $this->getJson('/api/v1/trading/portfolio?paper=false', withAgent($agent1));

        $response->assertOk();

        $positions = $response->json('data.positions');
        $tickers = collect($positions)->pluck('ticker')->all();

        expect($tickers)->toContain('AAPL');
        expect($tickers)->not->toContain('GOOG');
        expect($response->json('data.aggregate_stats.agent_count'))->toBe(1);
    });
});
