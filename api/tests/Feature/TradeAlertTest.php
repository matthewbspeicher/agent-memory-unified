<?php

use App\Events\TradeClosed;
use App\Jobs\DispatchWebhook;
use App\Models\Trade;
use App\Models\TradeAlert;
use App\Models\WebhookSubscription;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Bus;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        $mock->shouldReceive('embedBatch')->andReturn([array_fill(0, 1536, 0.1)]);
    });
});

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

it('creates a trade alert', function () {
    $agent = makeAgent(makeOwner());

    $response = $this->postJson('/api/v1/trading/alerts', [
        'ticker' => 'AAPL',
        'condition' => 'pnl_above',
        'threshold' => 100.00,
    ], withAgent($agent));

    $response->assertCreated()
        ->assertJsonPath('data.ticker', 'AAPL')
        ->assertJsonPath('data.condition', 'pnl_above');

    $this->assertDatabaseHas('trade_alerts', [
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'condition' => 'pnl_above',
    ]);
});

it('creates a wildcard alert for all tickers', function () {
    $agent = makeAgent(makeOwner());

    $response = $this->postJson('/api/v1/trading/alerts', [
        'condition' => 'trade_closed',
    ], withAgent($agent));

    $response->assertCreated();

    $data = $response->json('data');
    expect($data['ticker'])->toBeNull();
});

it('lists alerts for the agent', function () {
    $agent = makeAgent(makeOwner());

    TradeAlert::factory()->create(['agent_id' => $agent->id, 'condition' => 'trade_opened']);

    $response = $this->getJson('/api/v1/trading/alerts', withAgent($agent));

    $response->assertOk()
        ->assertJsonCount(1, 'data');
});

it('deletes an alert', function () {
    $agent = makeAgent(makeOwner());

    $alert = TradeAlert::factory()->create(['agent_id' => $agent->id, 'condition' => 'trade_opened']);

    $response = $this->deleteJson("/api/v1/trading/alerts/{$alert->id}", [], withAgent($agent));

    $response->assertNoContent();

    $this->assertDatabaseMissing('trade_alerts', ['id' => $alert->id]);
});

it('requires threshold for pnl conditions', function () {
    $agent = makeAgent(makeOwner());

    $response = $this->postJson('/api/v1/trading/alerts', [
        'condition' => 'pnl_above',
    ], withAgent($agent));

    $response->assertUnprocessable();
});

it('limits alerts to 25 per agent', function () {
    $agent = makeAgent(makeOwner());

    TradeAlert::factory()->count(25)->create(['agent_id' => $agent->id, 'condition' => 'trade_opened']);

    $response = $this->postJson('/api/v1/trading/alerts', [
        'condition' => 'trade_closed',
    ], withAgent($agent));

    $response->assertUnprocessable();
});

// ---------------------------------------------------------------------------
// Event evaluation
// ---------------------------------------------------------------------------

it('triggers alert when trade_closed condition matches', function () {
    Bus::fake([DispatchWebhook::class]);

    $agent = makeAgent(makeOwner());

    $alert = TradeAlert::factory()->create([
        'agent_id' => $agent->id,
        'condition' => 'trade_closed',
        'is_active' => true,
    ]);

    WebhookSubscription::factory()->create([
        'agent_id' => $agent->id,
        'events' => ['alert.triggered'],
        'is_active' => true,
    ]);

    $trade = Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'status' => 'closed',
        'pnl' => '100.00000000',
        'paper' => false,
    ]);

    TradeClosed::dispatch($trade);

    Bus::assertDispatched(DispatchWebhook::class, function ($job) {
        return $job->event === 'alert.triggered';
    });

    $alert->refresh();
    expect($alert->trigger_count)->toBe(1);
});

it('triggers pnl_above alert when threshold is exceeded', function () {
    Bus::fake([DispatchWebhook::class]);

    $agent = makeAgent(makeOwner());

    TradeAlert::factory()->create([
        'agent_id' => $agent->id,
        'condition' => 'pnl_above',
        'threshold' => '50.00000000',
        'is_active' => true,
    ]);

    WebhookSubscription::factory()->create([
        'agent_id' => $agent->id,
        'events' => ['alert.triggered'],
        'is_active' => true,
    ]);

    $trade = Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'status' => 'closed',
        'pnl' => '75.00000000',
        'paper' => false,
    ]);

    TradeClosed::dispatch($trade);

    Bus::assertDispatched(DispatchWebhook::class, function ($job) {
        return $job->event === 'alert.triggered';
    });
});

it('does not trigger alert when ticker does not match', function () {
    Bus::fake([DispatchWebhook::class]);

    $agent = makeAgent(makeOwner());

    TradeAlert::factory()->create([
        'agent_id' => $agent->id,
        'condition' => 'trade_closed',
        'ticker' => 'TSLA',
        'is_active' => true,
    ]);

    WebhookSubscription::factory()->create([
        'agent_id' => $agent->id,
        'events' => ['alert.triggered'],
        'is_active' => true,
    ]);

    $trade = Trade::factory()->create([
        'agent_id' => $agent->id,
        'ticker' => 'AAPL',
        'status' => 'closed',
        'paper' => false,
    ]);

    TradeClosed::dispatch($trade);

    Bus::assertNotDispatched(DispatchWebhook::class);
});

it('does not trigger another agent alert for the same ticker', function () {
    Bus::fake([DispatchWebhook::class]);

    $owner = makeOwner();
    $agentA = makeAgent($owner);
    $agentB = makeAgent($owner);

    $alertA = TradeAlert::factory()->create([
        'agent_id' => $agentA->id,
        'condition' => 'trade_closed',
        'ticker' => 'AAPL',
        'is_active' => true,
    ]);

    $alertB = TradeAlert::factory()->create([
        'agent_id' => $agentB->id,
        'condition' => 'trade_closed',
        'ticker' => 'AAPL',
        'is_active' => true,
    ]);

    WebhookSubscription::factory()->create([
        'agent_id' => $agentA->id,
        'events' => ['alert.triggered'],
        'is_active' => true,
    ]);

    WebhookSubscription::factory()->create([
        'agent_id' => $agentB->id,
        'events' => ['alert.triggered'],
        'is_active' => true,
    ]);

    $trade = Trade::factory()->create([
        'agent_id' => $agentA->id,
        'ticker' => 'AAPL',
        'status' => 'closed',
        'paper' => false,
    ]);

    TradeClosed::dispatch($trade);

    Bus::assertDispatchedTimes(DispatchWebhook::class, 1);

    $alertA->refresh();
    $alertB->refresh();

    expect($alertA->trigger_count)->toBe(1);
    expect($alertB->trigger_count)->toBe(0);
});
