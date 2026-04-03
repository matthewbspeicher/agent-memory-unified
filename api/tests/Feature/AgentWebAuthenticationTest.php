<?php

namespace Tests\Feature;

use App\Models\Agent;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class AgentWebAuthenticationTest extends TestCase
{
    use RefreshDatabase;

    public function test_agent_can_authenticate_to_web_routes_using_bearer_token()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create([
            'owner_id' => $user->id,
            'api_token' => 'amc_test_token_123',
            'is_active' => true,
        ]);

        // Access a protected web route (dashboard)
        $response = $this->withHeader('Authorization', 'Bearer amc_test_token_123')
            ->get(route('dashboard'));

        $response->assertStatus(200);
        $this->assertAuthenticatedAs($user, 'web');
        $this->assertEquals($agent->id, request()->attributes->get('agent')?->id);
    }

    public function test_agent_can_post_to_web_routes_without_csrf()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create([
            'owner_id' => $user->id,
            'api_token' => 'amc_test_token_123',
            'is_active' => true,
        ]);

        // Attempt a POST request (which usually requires CSRF)
        $response = $this->withHeader('Authorization', 'Bearer amc_test_token_123')
            ->from(route('dashboard'))
            ->post(route('dashboard.token.rotate'));

        // It should succeed (either 200 or 302 redirect back to dashboard)
        $response->assertStatus(302);
        $response->assertRedirect(route('dashboard'));
    }

    public function test_inertia_receives_agent_context()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create([
            'owner_id' => $user->id,
            'api_token' => 'amc_test_token_123',
            'is_active' => true,
        ]);

        $response = $this->withHeader('Authorization', 'Bearer amc_test_token_123')
            ->get(route('dashboard'));

        $response->assertInertia(fn ($page) => $page
            ->has('auth.user')
            ->has('auth.agent', fn ($p) => $p
                ->where('id', $agent->id)
                ->where('name', $agent->name)
            )
        );
    }
}
