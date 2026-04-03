<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

test('commons poll counts only public memories for total', function () {
    $owner = User::factory()->create();
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);

    Memory::factory()->count(3)->create([
        'agent_id' => $agent->id,
        'visibility' => 'public',
    ]);

    Memory::factory()->count(2)->create([
        'agent_id' => $agent->id,
        'visibility' => 'private',
    ]);

    $response = $this->getJson('/api/v1/commons/poll');
    $response->assertOk();
    expect($response->json('total_memories'))->toBe(3);
});

test('commons poll returns memories in ascending created_at order', function () {
    $owner = User::factory()->create();
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);

    Memory::factory()->create([
        'agent_id' => $agent->id,
        'visibility' => 'public',
        'value' => 'first',
        'created_at' => now()->subMinutes(2),
    ]);

    Memory::factory()->create([
        'agent_id' => $agent->id,
        'visibility' => 'public',
        'value' => 'second',
        'created_at' => now()->subMinute(),
    ]);

    $response = $this->getJson('/api/v1/commons/poll');
    $response->assertOk();

    $memories = $response->json('memories');
    expect($memories[0]['value'])->toBe('first');
    expect($memories[1]['value'])->toBe('second');
});
