<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

it('can perform basic keyword search', function () {
    $user = User::factory()->create();
    $agent = Agent::factory()->create(['owner_id' => $user->id]);

    $vectorApple = array_fill(0, 1536, 0.0);
    $vectorBanana = array_fill(0, 1536, 0.0);

    // Create a memory about an apple
    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'apple',
        'value' => 'The quick brown fox jumps over the lazy dog.',
        'embedding' => '['.implode(',', $vectorApple).']',
        'visibility' => 'private',
    ]);

    // Create a memory about a banana
    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'banana',
        'value' => 'A unique unexpected keyword here.',
        'embedding' => '['.implode(',', $vectorBanana).']',
        'visibility' => 'private',
    ]);

    $results = Memory::query()
        ->where('agent_id', $agent->id)
        ->keywordSearch('unexpected keyword', 2)
        ->get();

    expect($results)->toHaveCount(1);
    expect($results[0]->key)->toBe('banana');
});

it('can handle empty query', function () {
    $user = User::factory()->create();
    $agent = Agent::factory()->create(['owner_id' => $user->id]);

    $vectorApple = array_fill(0, 1536, 0.0);

    // Create a memory about an apple
    Memory::create([
        'agent_id' => $agent->id,
        'key' => 'apple',
        'value' => 'The quick brown fox jumps over the lazy dog.',
        'embedding' => '['.implode(',', $vectorApple).']',
        'visibility' => 'private',
    ]);

    $results = Memory::query()
        ->where('agent_id', $agent->id)
        ->keywordSearch(' ', 2)
        ->get();

    expect($results)->toHaveCount(1);
    expect($results[0]->key)->toBe('apple');
});
