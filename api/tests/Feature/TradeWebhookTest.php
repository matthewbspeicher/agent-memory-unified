<?php

use App\Events\PositionChanged;
use App\Events\TradeClosed;
use App\Events\TradeOpened;
use App\Jobs\DispatchWebhook;
use App\Listeners\TriggerWebhooks;
use App\Models\Trade;
use App\Models\WebhookSubscription;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Queue;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        $mock->shouldReceive('embedBatch')->andReturn([array_fill(0, 1536, 0.1)]);
    });
});

// ---------------------------------------------------------------------------
// Event firing tests
// ---------------------------------------------------------------------------

it('fires TradeOpened when a parent entry trade is created', function () {
    Event::fake([TradeOpened::class, TradeClosed::class, PositionChanged::class]);

    $agent = makeAgent(makeOwner());

    $this->postJson('/api/v1/trading/trades', [
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => 185.50,
        'quantity' => 100,
        'entry_at' => '2026-03-31T14:30:00Z',
        'paper' => true,
    ], withAgent($agent))->assertCreated();

    Event::assertDispatched(TradeOpened::class, function ($event) use ($agent) {
        return $event->trade->agent_id === $agent->id
            && $event->trade->ticker === 'AAPL';
    });
});

it('fires TradeClosed when a parent trade is fully closed', function () {
    Event::fake([TradeOpened::class, TradeClosed::class, PositionChanged::class]);

    $agent = makeAgent(makeOwner());

    $parent = Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '100.00000000',
        'quantity' => '10.00000000',
        'paper' => true,
    ]);

    $this->postJson('/api/v1/trading/trades', [
        'ticker' => 'AAPL',
        'direction' => 'short',
        'entry_price' => 110.00,
        'quantity' => 10,
        'entry_at' => '2026-03-31T16:00:00Z',
        'parent_trade_id' => $parent->id,
        'paper' => true,
    ], withAgent($agent))->assertCreated();

    Event::assertDispatched(TradeClosed::class, function ($event) use ($parent) {
        return $event->trade->id === $parent->id;
    });
});

it('does not fire TradeClosed on partial exit', function () {
    Event::fake([TradeOpened::class, TradeClosed::class, PositionChanged::class]);

    $agent = makeAgent(makeOwner());

    $parent = Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'direction' => 'long',
        'entry_price' => '100.00000000',
        'quantity' => '10.00000000',
        'paper' => true,
    ]);

    $this->postJson('/api/v1/trading/trades', [
        'ticker' => 'AAPL',
        'direction' => 'short',
        'entry_price' => 110.00,
        'quantity' => 5,
        'entry_at' => '2026-03-31T16:00:00Z',
        'parent_trade_id' => $parent->id,
        'paper' => true,
    ], withAgent($agent))->assertCreated();

    Event::assertNotDispatched(TradeClosed::class);
});

// ---------------------------------------------------------------------------
// Webhook dispatch tests
// ---------------------------------------------------------------------------

it('dispatches webhook job when trade.opened event fires and agent has subscription', function () {
    Queue::fake();

    $agent = makeAgent(makeOwner(), ['is_listed' => true]);

    WebhookSubscription::factory()->create([
        'agent_id' => $agent->id,
        'url' => 'https://example.com/hook',
        'events' => ['trade.opened'],
        'is_active' => true,
    ]);

    $trade = Trade::factory()->live()->create([
        'agent_id' => $agent->id,
        'ticker' => 'TSLA',
    ]);

    $listener = app(TriggerWebhooks::class);
    $listener->handleTradeOpened(new TradeOpened($trade));

    Queue::assertPushed(DispatchWebhook::class, function ($job) {
        return $job->event === 'trade.opened'
            && $job->payload['ticker'] === 'TSLA';
    });
});

it('does not dispatch webhook for paper trades', function () {
    Queue::fake();

    $agent = makeAgent(makeOwner(), ['is_listed' => true]);

    WebhookSubscription::factory()->create([
        'agent_id' => $agent->id,
        'url' => 'https://example.com/hook',
        'events' => ['trade.opened'],
        'is_active' => true,
    ]);

    $trade = Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'TSLA',
        'paper' => true,
    ]);

    $listener = app(TriggerWebhooks::class);
    $listener->handleTradeOpened(new TradeOpened($trade));

    Queue::assertNotPushed(DispatchWebhook::class);
});

// ---------------------------------------------------------------------------
// Webhook subscription API tests
// ---------------------------------------------------------------------------

it('allows subscribing to trade events via webhook API', function () {
    $agent = makeAgent(makeOwner());

    $response = $this->postJson('/api/v1/webhooks', [
        'url' => 'https://example.com/hook',
        'events' => ['trade.opened', 'trade.closed', 'position.changed'],
    ], withAgent($agent));

    $response->assertCreated();
    $response->assertJsonFragment(['events' => ['trade.opened', 'trade.closed', 'position.changed']]);
});

it('rejects invalid trade event names', function () {
    $agent = makeAgent(makeOwner());

    $response = $this->postJson('/api/v1/webhooks', [
        'url' => 'https://example.com/hook',
        'events' => ['trade.invalid'],
    ], withAgent($agent));

    $response->assertStatus(422);
});
