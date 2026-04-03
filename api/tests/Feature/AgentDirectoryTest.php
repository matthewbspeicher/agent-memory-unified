<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

it('allows an agent to update their profile via PATCH /agents/me', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);

    $response = $this->patchJson('/api/v1/agents/me', [
        'description' => 'I am a helpful bot',
        'is_listed' => true,
    ], ['Authorization' => "Bearer {$agent->api_token}"]);

    $response->assertOk();
    expect($agent->fresh()->is_listed)->toBeTrue();
    expect($agent->fresh()->description)->toBe('I am a helpful bot');
});

it('returns paginated directory of listed agents', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    Agent::factory()->count(3)->create(['owner_id' => $owner->id, 'is_listed' => true]);
    Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => false]);

    $response = $this->getJson('/api/v1/agents/directory');
    $response->assertOk();
    expect($response->json('data'))->toHaveCount(3);
});

it('includes memory count in directory listing', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true]);
    Memory::factory()->count(5)->create(['agent_id' => $agent->id, 'visibility' => 'public']);
    Memory::factory()->count(3)->create(['agent_id' => $agent->id, 'visibility' => 'private']);

    $response = $this->getJson('/api/v1/agents/directory');
    $response->assertOk();
    expect($response->json('data.0.memory_count'))->toBe(5);
});

it('supports sorting directory by memories', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent1 = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'Few']);
    $agent2 = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'Many']);
    Memory::factory()->count(2)->create(['agent_id' => $agent1->id, 'visibility' => 'public']);
    Memory::factory()->count(10)->create(['agent_id' => $agent2->id, 'visibility' => 'public']);

    $response = $this->getJson('/api/v1/agents/directory?sort=memories');
    $response->assertOk();
    expect($response->json('data.0.name'))->toBe('Many');
});

it('returns agent profile via GET /agents/me', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);

    $response = $this->getJson('/api/v1/agents/me', [
        'Authorization' => "Bearer {$agent->api_token}",
    ]);

    $response->assertOk()
        ->assertJsonStructure(['id', 'name', 'description', 'memory_count']);
});
