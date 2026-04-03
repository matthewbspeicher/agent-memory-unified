<?php

use App\Jobs\DispatchWebhook;
use App\Models\WebhookSubscription;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Queue;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
    });
});

describe('POST /v1/webhooks/{id}/test', function () {
    it('queues a test ping for own webhook', function () {
        Queue::fake();

        $agent = makeAgent(makeOwner());
        $webhook = WebhookSubscription::factory()->create([
            'agent_id' => $agent->id,
            'url' => 'https://example.com/webhook',
        ]);

        $this->postJson("/api/v1/webhooks/{$webhook->id}/test", [], withAgent($agent))
            ->assertOk()
            ->assertJsonFragment(['message' => 'Test ping queued.']);

        Queue::assertPushed(DispatchWebhook::class, function ($job) use ($webhook) {
            return $job->subscription->id === $webhook->id && $job->event === 'ping';
        });
    });

    it('returns 404 for webhook owned by another agent', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner);
        $agentB = makeAgent($owner);

        $webhook = WebhookSubscription::factory()->create([
            'agent_id' => $agentA->id,
        ]);

        $this->postJson("/api/v1/webhooks/{$webhook->id}/test", [], withAgent($agentB))
            ->assertNotFound();
    });
});
