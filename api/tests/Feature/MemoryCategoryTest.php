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
        $mock->shouldReceive('summarize')->andReturn('Compacted.');
    });
});

// ---------------------------------------------------------------------------
// Memory Categories
// ---------------------------------------------------------------------------

describe('Memory Categories', function () {

    it('stores a memory with a category', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories', [
            'key' => 'pref-dark-mode',
            'value' => 'User prefers dark mode',
            'category' => 'preferences',
        ], withAgent($agent))
            ->assertCreated()
            ->assertJsonPath('category', 'preferences');
    });

    it('category is optional and defaults to null', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories', [
            'key' => 'no-category',
            'value' => 'No category here',
        ], withAgent($agent))
            ->assertCreated()
            ->assertJsonPath('category', null);
    });

    it('filters list by category', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'pref1', 'value' => 'v1', 'category' => 'preferences']);
        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'task1', 'value' => 'v2', 'category' => 'tasks']);
        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'pref2', 'value' => 'v3', 'category' => 'preferences']);

        $this->getJson('/api/v1/memories?category=preferences', withAgent($agent))
            ->assertOk()
            ->assertJsonCount(2, 'data');
    });

    it('updates memory category', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'recategorize',
            'value' => 'Some value',
            'category' => 'old-category',
        ]);

        $this->patchJson('/api/v1/memories/recategorize', [
            'category' => 'new-category',
        ], withAgent($agent))
            ->assertOk()
            ->assertJsonPath('category', 'new-category');
    });

    it('rejects category over 100 chars', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories', [
            'key' => 'long-cat',
            'value' => 'test',
            'category' => str_repeat('a', 101),
        ], withAgent($agent))
            ->assertUnprocessable();
    });

    it('includes category in search results', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'cat-search',
            'value' => 'searchable content',
            'category' => 'skills',
        ]);

        $this->getJson('/api/v1/memories/search?q=searchable', withAgent($agent))
            ->assertOk()
            ->assertJsonPath('data.0.category', 'skills');
    });
});
