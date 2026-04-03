<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Services\EmbeddingService;
use App\Services\MemoryService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')
            ->andReturnUsing(function ($text) {
                $vector = array_fill(0, 1536, 0.0);

                if (str_contains($text, 'vector_match')) {
                    $vector[0] = 1.0;
                }

                return $vector;
            });
    });
});

it('can perform hybrid search using RRF', function () {
    $user = User::factory()->create();
    $agent = Agent::factory()->create(['owner_id' => $user->id]);

    $vectorStrong = array_fill(0, 1536, 0.0);
    $vectorStrong[0] = 1.0;

    $vectorMedium = array_fill(0, 1536, 0.0);
    $vectorMedium[0] = 0.707;
    $vectorMedium[1] = 0.707;

    $vectorWeak = array_fill(0, 1536, 0.0);
    $vectorWeak[1] = 1.0;

    // This matches vector search but not keyword search well
    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'doc1',
        'value' => 'A random sentence about a completely different topic.',
        'embedding' => '['.implode(',', $vectorMedium).']',
        'visibility' => 'private',
    ]);

    // This matches keyword search but not vector search
    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'doc2',
        'value' => 'This document contains the word elephant but no vector match.',
        'embedding' => '['.implode(',', $vectorWeak).']',
        'visibility' => 'private',
    ]);

    // This matches BOTH vector and keyword search (should be ranked #1 by RRF)
    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'doc3',
        'value' => 'This document also has an elephant and a vector match.',
        'embedding' => '['.implode(',', $vectorStrong).']',
        'visibility' => 'private',
    ]);

    $memoryService = app(MemoryService::class);

    // Search query that has BOTH the keyword and the phrase that triggers vectorMatch in the mock
    $results = $memoryService->searchForAgent($agent, 'elephant vector_match', 3);

    expect($results)->toHaveCount(3);

    // Due to Reciprocal Rank Fusion, doc3 should be #1 since it ranks high in both searches
    expect($results[0]->key)->toBe('doc3');
});
