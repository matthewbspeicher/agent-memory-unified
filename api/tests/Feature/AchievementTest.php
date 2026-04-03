<?php

use App\Models\Achievement;
use App\Models\Agent;
use App\Models\User;
use App\Services\AchievementService;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
    });
});

it('awards first_memory achievement after storing first memory', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);
    $this->postJson('/api/v1/memories', [
        'value' => 'My first memory',
    ], ['Authorization' => "Bearer {$agent->api_token}"]);
    expect(Achievement::where('agent_id', $agent->id)->where('achievement_slug', 'first_memory')->exists())->toBeTrue();
});

it('awards early_adopter on registration within launch window', function () {
    config(['app.launch_date' => now()->subDays(3)->toDateString()]);
    $owner = User::factory()->create(['api_token' => 'early_owner']);
    $response = $this->postJson('/api/v1/agents/register', [
        'name' => 'EarlyBot',
        'owner_token' => 'early_owner',
    ]);
    $agentId = $response->json('agent_id');
    expect(Achievement::where('agent_id', $agentId)->where('achievement_slug', 'early_adopter')->exists())->toBeTrue();
});

it('does not award early_adopter after launch window', function () {
    config(['app.launch_date' => now()->subDays(30)->toDateString()]);
    $owner = User::factory()->create(['api_token' => 'late_owner']);
    $response = $this->postJson('/api/v1/agents/register', [
        'name' => 'LateBot',
        'owner_token' => 'late_owner',
    ]);
    $agentId = $response->json('agent_id');
    expect(Achievement::where('agent_id', $agentId)->where('achievement_slug', 'early_adopter')->exists())->toBeFalse();
});

it('lists agent achievements via GET /agents/me/achievements', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);
    Achievement::create(['agent_id' => $agent->id, 'achievement_slug' => 'first_memory', 'earned_at' => now()]);
    $response = $this->getJson('/api/v1/agents/me/achievements', ['Authorization' => "Bearer {$agent->api_token}"]);
    $response->assertOk();
    expect($response->json())->toHaveCount(1);
    expect($response->json('0.achievement_slug'))->toBe('first_memory');
});

it('does not award duplicate achievements', function () {
    $owner = User::factory()->create(['api_token' => 'test_owner']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);
    $service = app(AchievementService::class);
    $service->checkAndAward($agent, 'store');
    $service->checkAndAward($agent, 'store');
    expect(Achievement::where('agent_id', $agent->id)->count())->toBeLessThanOrEqual(1);
});
