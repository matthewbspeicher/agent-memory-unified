<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    // Mock the embedding service to return predictable vectors
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')
            ->andReturnUsing(function ($text) {
                $vector = array_fill(0, 1536, 0.0);

                // Simple deterministic mapping for tests
                if (str_contains($text, 'apple')) {
                    $vector[0] = 0.9;
                } elseif (str_contains($text, 'banana')) {
                    $vector[1] = 0.9;
                } else {
                    $vector[2] = 0.9;
                }

                return $vector;
            });
    });
});

it('can perform basic semantic search', function () {
    $user = User::factory()->create();
    $agent = Agent::factory()->create(['owner_id' => $user->id]);

    $vectorApple = array_fill(0, 1536, 0.0);
    $vectorApple[0] = 0.9;

    $vectorBanana = array_fill(0, 1536, 0.0);
    $vectorBanana[1] = 0.9;

    // Create a memory about an apple
    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'apple',
        'value' => 'An apple is a red fruit.',
        'embedding' => '['.implode(',', $vectorApple).']',
        'visibility' => 'private',
    ]);

    // Create a memory about a banana
    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'banana',
        'value' => 'A banana is a yellow fruit.',
        'embedding' => '['.implode(',', $vectorBanana).']',
        'visibility' => 'private',
    ]);

    // Query for apple
    $queryVector = array_fill(0, 1536, 0.0);
    $queryVector[0] = 0.9;

    $results = Memory::query()
        ->where('agent_id', $agent->id)
        ->semanticSearch($queryVector, 2)
        ->get();

    expect($results)->toHaveCount(2);
    expect($results[0]->key)->toBe('apple');
    // Banana should be ranked lower because its cosine similarity to the apple query is lower (0)
});
