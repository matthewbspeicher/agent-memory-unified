<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;

uses(RefreshDatabase::class);

beforeEach(function () {
    Cache::flush();
});

it('returns platform stats without authentication', function () {
    $response = $this->getJson('/api/v1/stats');
    $response->assertOk()
        ->assertJsonStructure([
            'agents_registered',
            'memories_stored',
            'searches_performed',
            'commons_memories',
            'uptime_days',
        ]);
});

it('returns accurate agent and memory counts', function () {
    // Capture baseline counts before creating test data
    $baselineAgents = Agent::count();
    $baselineMemories = Memory::count();
    $baselinePublic = Memory::where('visibility', 'public')->count();

    $owner = User::factory()->create(['api_token' => 'test_owner_token']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);
    Memory::factory()->count(3)->create(['agent_id' => $agent->id, 'visibility' => 'private']);
    Memory::factory()->count(2)->create(['agent_id' => $agent->id, 'visibility' => 'public']);

    $response = $this->getJson('/api/v1/stats');
    $response->assertOk();
    expect($response->json('agents_registered'))->toBe($baselineAgents + 1);
    expect($response->json('memories_stored'))->toBe($baselineMemories + 5);
    expect($response->json('commons_memories'))->toBe($baselinePublic + 2);
});
