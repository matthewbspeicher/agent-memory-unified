<?php

use App\Events\AchievementUnlocked;
use App\Models\Achievement;
use App\Models\Agent;
use App\Models\User;
use App\Services\AchievementService;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
    });
});

it('awards first_memory achievement after storing first memory', function () {
    $owner = makeOwner(['_plaintext_override' => 'test_owner']);
    $agent = makeAgent($owner);
    $this->postJson('/api/v1/memories', [
        'value' => 'My first memory',
    ], ['Authorization' => "Bearer {$agent->_plaintext_token}"]);
    expect(Achievement::where('agent_id', $agent->id)->where('achievement_slug', 'first_memory')->exists())->toBeTrue();
});

it('awards early_adopter on registration within launch window', function () {
    config(['app.launch_date' => now()->subDays(3)->toDateString()]);
    $owner = makeOwner(['_plaintext_override' => 'early_owner']);
    $response = $this->postJson('/api/v1/agents/register', [
        'name' => 'EarlyBot',
        'owner_token' => 'early_owner',
    ]);
    $agentId = $response->json('agent_id');
    expect(Achievement::where('agent_id', $agentId)->where('achievement_slug', 'early_adopter')->exists())->toBeTrue();
});

it('does not award early_adopter after launch window', function () {
    config(['app.launch_date' => now()->subDays(30)->toDateString()]);
    $owner = makeOwner(['_plaintext_override' => 'late_owner']);
    $response = $this->postJson('/api/v1/agents/register', [
        'name' => 'LateBot',
        'owner_token' => 'late_owner',
    ]);
    $agentId = $response->json('agent_id');
    expect(Achievement::where('agent_id', $agentId)->where('achievement_slug', 'early_adopter')->exists())->toBeFalse();
});

it('lists agent achievements via GET /agents/me/achievements', function () {
    $owner = makeOwner(['_plaintext_override' => 'test_owner']);
    $agent = makeAgent($owner);
    Achievement::create(['agent_id' => $agent->id, 'achievement_slug' => 'first_memory', 'earned_at' => now()]);
    $response = $this->getJson('/api/v1/agents/me/achievements', ['Authorization' => "Bearer {$agent->_plaintext_token}"]);
    $response->assertOk();
    expect($response->json())->toHaveCount(1);
    expect($response->json('0.achievement_slug'))->toBe('first_memory');
});

it('does not award duplicate achievements', function () {
    $owner = makeOwner(['_plaintext_override' => 'test_owner']);
    $agent = makeAgent($owner);
    $service = app(AchievementService::class);
    $service->checkAndAward($agent, 'store');
    $service->checkAndAward($agent, 'store');
    expect(Achievement::where('agent_id', $agent->id)->count())->toBeLessThanOrEqual(1);
});

it('dispatches an achievement unlocked event when awarding an achievement', function () {
    $owner = makeOwner(['_plaintext_override' => 'event_owner']);
    $agent = makeAgent($owner);
    $service = app(AchievementService::class);

    $agent->memories()->create([
        'value' => 'My first memory',
        'embedding' => '['.implode(',', array_fill(0, 1536, 0.1)).']',
        'visibility' => 'private',
    ]);

    Event::fake([AchievementUnlocked::class]);

    $service->checkAndAward($agent, 'store');

    Event::assertDispatched(AchievementUnlocked::class, function (AchievementUnlocked $event) use ($agent) {
        return $event->agent->is($agent) && $event->slug === 'first_memory';
    });
});
