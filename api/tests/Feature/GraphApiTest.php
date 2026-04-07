<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(\App\Contracts\EmbeddingServiceInterface::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
    });
});

it('returns authenticated agent graph with nodes and edges', function () {
    $owner = makeOwner(['_plaintext_override' => 'test_owner']);
    $agent = makeAgent($owner);
    $m1 = Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'mem1', 'type' => 'fact']);
    $m2 = Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'mem2', 'type' => 'preference']);
    $m1->relatedTo()->attach($m2->id, ['type' => 'relates_to']);

    $response = $this->getJson('/api/v1/agents/me/graph', [
        'Authorization' => "Bearer {$agent->_plaintext_token}",
    ]);

    $response->assertOk()->assertJsonStructure(['nodes', 'edges']);
    expect($response->json('nodes'))->toHaveCount(2);
    expect($response->json('edges'))->toHaveCount(1);
    expect($response->json('edges.0.relation'))->toBe('relates_to');
});

it('returns public graph with only public memories', function () {
    $owner = makeOwner(['_plaintext_override' => 'test_owner']);
    $agent = makeAgent($owner);
    Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'public']);
    Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'private']);

    $response = $this->getJson("/api/v1/agents/{$agent->id}/graph");
    $response->assertOk();
    expect($response->json('nodes'))->toHaveCount(1);
});

it('limits graph to 200 nodes', function () {
    $owner = makeOwner(['_plaintext_override' => 'test_owner']);
    $agent = makeAgent($owner);
    Memory::factory()->count(210)->create(['agent_id' => $agent->id]);

    $response = $this->getJson('/api/v1/agents/me/graph', [
        'Authorization' => "Bearer {$agent->_plaintext_token}",
    ]);
    $response->assertOk();
    expect(count($response->json('nodes')))->toBeLessThanOrEqual(200);
});
