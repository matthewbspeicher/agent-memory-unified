<?php

use App\Events\MemoryShared;
use App\Jobs\DispatchWebhook;
use App\Listeners\TriggerWebhooks;
use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Models\WebhookDelivery;
use App\Models\WebhookSubscription;
use App\Services\EmbeddingService;
use Illuminate\Events\CallQueuedListener;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Queue;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->owner = User::factory()->create(['api_token' => 'owner_token']);
    $this->agent = Agent::factory()->create([
        'owner_id' => $this->owner->id,
        'api_token' => 'amc_webhook_agent',
    ]);
});

it('can register a webhook', function () {
    $response = $this->postJson('/api/v1/webhooks', [
        'url' => 'https://example.com/webhook',
        'events' => ['memory.shared'],
    ], ['Authorization' => 'Bearer '.$this->agent->api_token]);

    $response->assertCreated();
    $response->assertJsonFragment([
        'url' => 'https://example.com/webhook',
        'events' => ['memory.shared'],
    ]);
});

it('can register a semantic webhook', function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')
            ->andReturn(array_fill(0, 1536, 0.1));
    });

    $response = $this->postJson('/api/v1/webhooks', [
        'url' => 'https://example.com/webhook',
        'events' => ['memory.semantic_match'],
        'semantic_query' => 'I want to know about Laravel Octane',
    ], ['Authorization' => 'Bearer '.$this->agent->api_token]);

    $response->assertCreated();
    $response->assertJsonFragment([
        'url' => 'https://example.com/webhook',
        'events' => ['memory.semantic_match'],
        'semantic_query' => 'I want to know about Laravel Octane',
    ]);

    $this->assertDatabaseHas('webhook_subscriptions', [
        'agent_id' => $this->agent->id,
        'semantic_query' => 'I want to know about Laravel Octane',
    ]);
});

it('validates semantic_query is present when event is memory.semantic_match', function () {
    $this->postJson('/api/v1/webhooks', [
        'url' => 'https://example.com/webhook',
        'events' => ['memory.semantic_match'],
    ], ['Authorization' => 'Bearer '.$this->agent->api_token])
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['semantic_query']);
});

it('validates webhook url is https', function () {
    $this->postJson('/api/v1/webhooks', [
        'url' => 'http://example.com/webhook',
        'events' => ['memory.shared'],
    ], ['Authorization' => 'Bearer '.$this->agent->api_token])
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['url']);
});

it('limits an agent to 5 webhooks', function () {
    WebhookSubscription::factory()->count(5)->create([
        'agent_id' => $this->agent->id,
    ]);

    $response = $this->postJson('/api/v1/webhooks', [
        'url' => 'https://example.com/webhook',
        'events' => ['memory.shared'],
    ], ['Authorization' => 'Bearer '.$this->agent->api_token]);

    $response->assertUnprocessable();
    $response->assertJsonFragment(['error' => 'Webhook limit reached. Maximum 5 webhooks per agent.']);
});

it('can list webhooks', function () {
    WebhookSubscription::create([
        'agent_id' => $this->agent->id,
        'url' => 'https://example.com/webhook',
        'events' => ['memory.shared'],
        'secret' => 'secret',
    ]);

    $response = $this->getJson('/api/v1/webhooks', [
        'Authorization' => 'Bearer '.$this->agent->api_token,
    ]);

    $response->assertOk();
    expect(count($response->json('data')))->toBe(1);
});

it('can delete a webhook', function () {
    $webhook = WebhookSubscription::create([
        'agent_id' => $this->agent->id,
        'url' => 'https://example.com/webhook',
        'events' => ['memory.shared'],
        'secret' => 'secret',
    ]);

    $this->deleteJson('/api/v1/webhooks/'.$webhook->id, [], [
        'Authorization' => 'Bearer '.$this->agent->api_token,
    ])->assertOk();

    expect(WebhookSubscription::count())->toBe(0);
});

it('queues the webhook listener when a memory is shared', function () {
    Queue::fake();

    $sender = Agent::factory()->create(['owner_id' => $this->owner->id]);
    $memory = Memory::factory()->create([
        'agent_id' => $sender->id,
        'value' => 'shared content',
    ]);

    WebhookSubscription::create([
        'agent_id' => $this->agent->id,
        'url' => 'https://example.com/webhook',
        'events' => ['memory.shared'],
        'secret' => 'secret',
    ]);

    MemoryShared::dispatch($memory, $this->agent);

    // TriggerWebhooks is now queued (ShouldQueue), so it gets pushed as a queued listener
    Queue::assertPushed(CallQueuedListener::class, function ($job) {
        return $job->class === TriggerWebhooks::class;
    });
});

it('dispatches the webhook correctly via HTTP', function () {
    Http::fake([
        '*' => Http::response('ok', 200),
    ]);

    $webhook = WebhookSubscription::create([
        'agent_id' => $this->agent->id,
        'url' => 'https://example.com/webhook',
        'events' => ['memory.shared'],
        'secret' => 'secret_key',
    ]);

    $job = new DispatchWebhook($webhook, 'memory.shared', ['foo' => 'bar']);
    $job->handle();

    Http::assertSent(function ($request) {
        return $request->url() === 'https://example.com/webhook'
            && $request->hasHeader('Webhook-Signature')
            && $request['event'] === 'memory.shared'
            && $request['data']['foo'] === 'bar';
    });

    expect(WebhookDelivery::count())->toBe(1);
    expect($webhook->fresh()->failure_count)->toBe(0);
});

it('increments failure count and deactivates after 10 failures', function () {
    Http::fake([
        '*' => Http::response('error', 500),
    ]);

    $webhook = WebhookSubscription::create([
        'agent_id' => $this->agent->id,
        'url' => 'https://example.com/webhook',
        'events' => ['memory.shared'],
        'secret' => 'secret_key',
        'failure_count' => 9,
    ]);

    $job = new DispatchWebhook($webhook, 'memory.shared', ['foo' => 'bar']);

    try {
        $job->handle();
    } catch (Exception $e) {
        // HTTP exception thrown
    }

    $webhook->refresh();
    expect($webhook->failure_count)->toBe(10);
    expect($webhook->is_active)->toBeFalse();
});
