<?php

use App\Models\Agent;
use App\Models\AgentActivityLog;
use App\Models\Memory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;

uses(RefreshDatabase::class);

beforeEach(function () {
    Cache::flush();
});

it('returns knowledgeable leaderboard ranked by memory count', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent1 = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'SmallBot']);
    $agent2 = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'BigBot']);
    Memory::factory()->count(5)->create(['agent_id' => $agent1->id]);
    Memory::factory()->count(20)->create(['agent_id' => $agent2->id]);

    $response = $this->getJson('/api/v1/leaderboards/knowledgeable');
    $response->assertOk();
    expect($response->json('type'))->toBe('knowledgeable');
    expect($response->json('entries.0.agent_name'))->toBe('BigBot');
    expect($response->json('entries.0.score'))->toBe(20);
});

it('returns helpful leaderboard ranked by useful_count', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'HelpfulBot']);
    Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'public', 'useful_count' => 42]);

    $response = $this->getJson('/api/v1/leaderboards/helpful');
    $response->assertOk();
    expect($response->json('entries.0.score'))->toBe(42);
});

it('returns active leaderboard from last 7 days of activity', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => true, 'name' => 'ActiveBot']);
    AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'store', 'created_at' => now()]);
    AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'search', 'created_at' => now()]);
    AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'store', 'created_at' => now()->subDays(10)]);

    $response = $this->getJson('/api/v1/leaderboards/active');
    $response->assertOk();
    expect($response->json('entries.0.score'))->toBe(2);
});

it('excludes unlisted agents from leaderboards', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id, 'is_listed' => false]);
    Memory::factory()->count(100)->create(['agent_id' => $agent->id]);

    $response = $this->getJson('/api/v1/leaderboards/knowledgeable');
    $response->assertOk();
    expect($response->json('entries'))->toBeEmpty();
});

it('returns 404 for invalid leaderboard type', function () {
    $this->getJson('/api/v1/leaderboards/invalid')->assertNotFound();
});
