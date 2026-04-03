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

describe('Memory quota enforcement', function () {
    it('rejects memory creation when quota is full', function () {
        $agent = makeAgent(makeOwner(), ['max_memories' => 2]);

        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'm1']);
        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'm2']);

        $this->postJson('/api/v1/memories', [
            'value' => 'should fail',
        ], withAgent($agent))
            ->assertStatus(422);
    });

    it('allows upsert when key already exists even at quota', function () {
        $agent = makeAgent(makeOwner(), ['max_memories' => 1]);

        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'existing']);

        $this->postJson('/api/v1/memories', [
            'key' => 'existing',
            'value' => 'updated value',
        ], withAgent($agent))
            ->assertCreated();
    });
});
