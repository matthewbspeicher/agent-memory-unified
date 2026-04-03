<?php

use App\Models\Agent;
use App\Models\User;
use App\Services\EmbeddingService;
use Illuminate\Cache\RateLimiting\Limit;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\RateLimiter;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')
            ->andReturn(array_fill(0, 1536, 0.1));
        $mock->shouldReceive('embedBatch')
            ->andReturn([array_fill(0, 1536, 0.1)]);
    });

    $this->owner = User::factory()->create(['api_token' => 'owner_test_token']);
    $this->agent = Agent::factory()->create([
        'owner_id' => $this->owner->id,
        'api_token' => 'amc_rate_limit_test',
    ]);
});

it('returns rate limit headers on API responses', function () {
    // Override rate limiter to apply in tests
    RateLimiter::for('api', fn () => Limit::perMinute(60));
    RateLimiter::for('agent_api', fn () => Limit::perMinute(10));

    $response = $this->getJson('/api/v1/memories', [
        'Authorization' => 'Bearer amc_rate_limit_test',
    ]);

    $response->assertOk();
    $response->assertHeader('X-RateLimit-Limit');
    $response->assertHeader('X-RateLimit-Remaining');
});

it('returns 429 when agent API rate limit is exceeded', function () {
    // Set a very low limit for testing
    RateLimiter::for('api', fn () => Limit::perMinute(100));
    RateLimiter::for('agent_api', fn () => Limit::perMinute(2));

    $headers = ['Authorization' => 'Bearer amc_rate_limit_test'];

    // First two requests should pass
    $this->getJson('/api/v1/memories', $headers)->assertOk();
    $this->getJson('/api/v1/memories', $headers)->assertOk();

    // Third should be throttled
    $this->getJson('/api/v1/memories', $headers)->assertStatus(429);
});

it('returns 429 when public API rate limit is exceeded', function () {
    RateLimiter::for('api', fn () => Limit::perMinute(2));

    // Hit a public endpoint (agent profile) — doesn't need auth
    $agentId = $this->agent->id;

    $this->getJson("/api/v1/agents/{$agentId}")->assertOk();
    $this->getJson("/api/v1/agents/{$agentId}")->assertOk();
    $this->getJson("/api/v1/agents/{$agentId}")->assertStatus(429);
});

it('throttles magic link login requests', function () {
    // The route already has throttle:3,1 middleware
    // We need to override the global 'api' limiter but the magic link
    // uses its own inline throttle on the web route — that works in tests
    // because it doesn't check app()->environment('testing')

    for ($i = 0; $i < 3; $i++) {
        $this->post('/login', [
            '_token' => csrf_token(),
            'email' => "test{$i}@example.com",
        ]);
    }

    $response = $this->post('/login', [
        '_token' => csrf_token(),
        'email' => 'throttled@example.com',
    ]);

    $response->assertStatus(429);
});
