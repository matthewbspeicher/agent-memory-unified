<?php

use App\Models\WebhookSubscription;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
    });
});

describe('Webhook secret visibility', function () {
    it('shows secret on creation', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/webhooks', [
            'url' => 'https://example.com/webhook',
            'events' => ['memory.shared'],
        ], withAgent($agent));

        $response->assertCreated();
        expect($response->json('secret'))->toStartWith('whsec_');
    });

    it('hides secret in list endpoint', function () {
        $agent = makeAgent(makeOwner());

        WebhookSubscription::factory()->create(['agent_id' => $agent->id]);

        $response = $this->getJson('/api/v1/webhooks', withAgent($agent));

        $response->assertOk();
        $webhooks = $response->json('data');
        expect($webhooks)->toHaveCount(1);
        expect($webhooks[0])->not->toHaveKey('secret');
        expect($webhooks[0])->not->toHaveKey('embedding');
    });
});
