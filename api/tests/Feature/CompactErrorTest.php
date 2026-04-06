<?php

use App\Models\Memory;
use App\Services\EmbeddingService;
use App\Services\SummarizationService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
    });
});

describe('POST /v1/memories/compact error paths', function () {
    it('returns 422 when memory_ids validation fails', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories/compact', [
            'memory_ids' => ['nonexistent-uuid'],
            'summary_key' => 'summary',
        ], withAgent($agent))
            ->assertStatus(422);
    });

    it('returns 422 when fewer than 2 memory_ids provided', function () {
        $agent = makeAgent(makeOwner());
        $m1 = Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'm1']);

        $this->postJson('/api/v1/memories/compact', [
            'memory_ids' => [$m1->id],
            'summary_key' => 'summary',
        ], withAgent($agent))
            ->assertStatus(422);
    });

    it('returns 422 when summary_key is missing', function () {
        $agent = makeAgent(makeOwner());

        $m1 = Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'm1', 'value' => 'Fact 1']);
        $m2 = Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'm2', 'value' => 'Fact 2']);

        $this->postJson('/api/v1/memories/compact', [
            'memory_ids' => [$m1->id, $m2->id],
        ], withAgent($agent))
            ->assertStatus(422)
            ->assertJsonValidationErrors(['summary_key']);
    });
});
