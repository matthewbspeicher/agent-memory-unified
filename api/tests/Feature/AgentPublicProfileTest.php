<?php

use App\Models\Memory;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
    });
});

describe('GET /v1/agents/{agentId}', function () {
    it('returns agent public profile', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'public']);
        Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'private']);

        $response = $this->getJson("/api/v1/agents/{$agent->id}");

        $response->assertOk()
            ->assertJsonStructure(['id', 'name', 'description', 'memory_count', 'last_seen_at', 'member_since']);

        // memory_count should only include public memories
        expect($response->json('memory_count'))->toBe(1);
    });

    it('returns 404 for non-existent agent', function () {
        $this->getJson('/api/v1/agents/00000000-0000-0000-0000-000000000000')
            ->assertNotFound();
    });
});
