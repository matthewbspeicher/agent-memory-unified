<?php

use App\Models\Memory;
use App\Services\EmbeddingService;
use App\Services\SummarizationService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')
            ->andReturn(array_fill(0, 1536, 0.1));
    });

    $this->mock(SummarizationService::class, function ($mock) {
        $mock->shouldReceive('generateSummary')->andReturn(null);
    });
});

// ---------------------------------------------------------------------------
// Relevance Feedback
// ---------------------------------------------------------------------------

describe('Access Tracking', function () {

    it('increments access_count on GET /memories/{key}', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'tracked',
            'value' => 'Some value',
            'access_count' => 0,
        ]);

        $this->getJson('/api/v1/memories/tracked', withAgent($agent))
            ->assertOk();

        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'key' => 'tracked',
            'access_count' => 1,
        ]);

        // Second access
        $this->getJson('/api/v1/memories/tracked', withAgent($agent))
            ->assertOk();

        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'key' => 'tracked',
            'access_count' => 2,
        ]);
    });

    it('updates last_accessed_at on retrieval', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'timestamped',
            'value' => 'Some value',
            'last_accessed_at' => null,
        ]);

        $this->getJson('/api/v1/memories/timestamped', withAgent($agent))
            ->assertOk();

        $memory = Memory::where('key', 'timestamped')->first();
        expect($memory->last_accessed_at)->not->toBeNull();
    });
});

describe('POST /v1/memories/{key}/feedback', function () {

    it('increments useful_count when useful is true', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'useful-mem',
            'value' => 'Helpful content',
            'useful_count' => 0,
        ]);

        $this->postJson('/api/v1/memories/useful-mem/feedback', [
            'useful' => true,
        ], withAgent($agent))
            ->assertOk()
            ->assertJsonPath('message', 'Feedback recorded.');

        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'key' => 'useful-mem',
            'useful_count' => 1,
        ]);
    });

    it('does not increment useful_count when useful is false', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'not-useful',
            'value' => 'Unhelpful content',
            'useful_count' => 0,
        ]);

        $this->postJson('/api/v1/memories/not-useful/feedback', [
            'useful' => false,
        ], withAgent($agent))
            ->assertOk();

        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'key' => 'not-useful',
            'useful_count' => 0,
        ]);
    });

    it('rejects feedback on a non-existent memory', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories/nonexistent/feedback', [
            'useful' => true,
        ], withAgent($agent))
            ->assertNotFound();
    });

    it('requires the useful field', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'missing-useful',
            'value' => 'test',
        ]);

        $this->postJson('/api/v1/memories/missing-useful/feedback', [], withAgent($agent))
            ->assertUnprocessable();
    });

    it('returns access_count and useful_count in memory responses', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'counts-check',
            'value' => 'test',
            'access_count' => 5,
            'useful_count' => 3,
        ]);

        $this->getJson('/api/v1/memories/counts-check', withAgent($agent))
            ->assertOk()
            ->assertJsonPath('access_count', 6) // +1 from this GET
            ->assertJsonPath('useful_count', 3);
    });
});
