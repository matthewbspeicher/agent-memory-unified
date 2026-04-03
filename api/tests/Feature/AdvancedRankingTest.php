<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Services\EmbeddingService;
use App\Services\MemoryService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')
            ->andReturnUsing(function ($text) {
                // Return a dummy vector so the DB doesn't complain
                return array_fill(0, 1536, 0.1);
            });
    });
});

it('ranks highly important old memories above normal new memories', function () {
    $user = User::factory()->create();
    $agent = Agent::factory()->create(['owner_id' => $user->id]);

    $memoryService = app(MemoryService::class);
    $vector = array_fill(0, 1536, 0.1);

    // Old but VERY important
    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'old_important',
        'value' => 'The user absolutely hates the color red. This is critical.',
        'embedding' => '['.implode(',', $vector).']',
        'visibility' => 'private',
        'importance' => 10,
        'confidence' => 1.0,
        'created_at' => Carbon::now()->subDays(60), // 60 days old
    ]);

    // New but average importance
    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'new_normal',
        'value' => 'The user clicked a red button today.',
        'embedding' => '['.implode(',', $vector).']',
        'visibility' => 'private',
        'importance' => 5,
        'confidence' => 1.0,
        'created_at' => Carbon::now(), // brand new
    ]);

    // Both match the query via keyword search since both have "user" and "red"
    // Since vectors are identical, the base RRF score for vector search will be very close.
    // The importance multiplier (10 = 1.5x) should outweigh the 60-day time decay (~0.55x).

    $results = $memoryService->searchForAgent($agent, 'user red button color', 5);

    // Assert the older but much more important memory ranks first
    expect($results[0]->key)->toBe('old_important');
});

it('ranks confident memories above uncertain ones', function () {
    $user = User::factory()->create();
    $agent = Agent::factory()->create(['owner_id' => $user->id]);

    $memoryService = app(MemoryService::class);
    $vector = array_fill(0, 1536, 0.1);

    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'low_confidence',
        'value' => 'I think the user lives in New York but I am not sure.',
        'embedding' => '['.implode(',', $vector).']',
        'visibility' => 'private',
        'importance' => 5,
        'confidence' => 0.2, // very uncertain
        'created_at' => Carbon::now(),
    ]);

    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'high_confidence',
        'value' => 'The user lives in New York. They told me directly.',
        'embedding' => '['.implode(',', $vector).']',
        'visibility' => 'private',
        'importance' => 5,
        'confidence' => 1.0, // absolutely certain
        'created_at' => Carbon::now(),
    ]);

    $results = $memoryService->searchForAgent($agent, 'user location new york', 5);

    // The high confidence one should win easily
    expect($results[0]->key)->toBe('high_confidence');
});
