<?php

namespace Tests\Feature;

use Tests\TestCase;
use App\Models\Agent;
use App\Events\AgentDeactivated;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Redis;

class AgentDeactivationTest extends TestCase
{
    use RefreshDatabase;

    public function test_agent_can_deactivate_themselves()
    {
        Event::fake();

        $agent = Agent::factory()->create([
            'token_hash' => hash('sha256', 'amc_test_token'),
            'is_active' => true,
        ]);

        $response = $this->withHeaders([
            'Authorization' => 'Bearer amc_test_token',
        ])->postJson('/api/v1/agents/me/deactivate');

        $response->assertStatus(200);
        $response->assertJson([
            'message' => 'Agent deactivated. All tokens have been revoked.',
        ]);

        // Verify agent is marked inactive
        $agent->refresh();
        $this->assertFalse($agent->is_active);

        // Verify event was dispatched
        Event::assertDispatched(AgentDeactivated::class, function ($event) use ($agent) {
            return $event->agent->id === $agent->id;
        });
    }

    public function test_inactive_agent_cannot_authenticate()
    {
        $agent = Agent::factory()->create([
            'token_hash' => hash('sha256', 'amc_test_token'),
            'is_active' => false,
        ]);

        $response = $this->withHeaders([
            'Authorization' => 'Bearer amc_test_token',
        ])->getJson('/api/v1/agents/me');

        $response->assertStatus(401);
        $response->assertJson([
            'error' => 'Agent has been deactivated.',
        ]);
    }

    public function test_cannot_deactivate_already_inactive_agent()
    {
        $agent = Agent::factory()->create([
            'token_hash' => hash('sha256', 'amc_test_token'),
            'is_active' => false,
        ]);

        $response = $this->withHeaders([
            'Authorization' => 'Bearer amc_test_token',
        ])->postJson('/api/v1/agents/me/deactivate');

        // Note: This will fail auth before reaching the endpoint
        // because middleware blocks inactive agents
        $response->assertStatus(401);
    }

    public function test_revoke_agent_tokens_listener_adds_wildcard_to_redis()
    {
        $agent = Agent::factory()->create([
            'token_hash' => hash('sha256', 'amc_test_token'),
            'is_active' => true,
        ]);

        // Mock Redis
        Redis::shouldReceive('connection->client->sadd')
            ->once()
            ->with("revoked_tokens:{$agent->id}", '*');

        // Manually dispatch the event (since we're mocking Redis)
        event(new AgentDeactivated($agent));
    }
}
