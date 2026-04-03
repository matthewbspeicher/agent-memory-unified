<?php

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

    it('apportions parent fees on partial exit', function () {
        $service = app(TradingService::class);
        $agent = makeAgent(makeOwner());

        $parent = Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'long',
            'entry_price' => '100.00000000',
            'quantity' => '10.00000000',
            'fees' => '10.00000000',
            'paper' => true,
        ]);

        $child = Trade::factory()->create([
            'agent_id' => $agent->id,
            'ticker' => 'AAPL',
            'direction' => 'short',
            'entry_price' => '110.00000000',
            'quantity' => '5.00000000',
            'fees' => '2.00000000',
            'parent_trade_id' => $parent->id,
            'paper' => true,
        ]);

        $pnl = $service->computeChildPnl($child, $parent);

        // Gross PnL: (110 - 100) * 5 = 50
        // Parent fee share: 10 * (5 / 10) = 5
        // Total fees: 5 (share) + 2 (child) = 7
        // Net PnL: 50 - 7 = 43
        expect((float) $pnl['pnl'])->toBe(43.0);
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
