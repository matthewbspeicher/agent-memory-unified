<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class AgentWebAuthenticationTest extends TestCase
{
    use RefreshDatabase;

    public function test_authenticated_user_can_access_dashboard()
    {
        $user = makeOwner();

        $response = $this->actingAs($user)->get(route('dashboard'));

        $response->assertStatus(200);
    }

    public function test_unauthenticated_user_is_redirected_from_dashboard()
    {
        $response = $this->get(route('dashboard'));

        $response->assertRedirect('/login');
    }

    public function test_dashboard_json_includes_agent_data()
    {
        $user = makeOwner();
        $agent = makeAgent($user);

        $response = $this->actingAs($user)->get(route('dashboard'));

        $response->assertOk();
        $response->assertJson(fn ($json) => $json
            ->where('hasApiToken', true)
            ->has('agents', 1)
            ->etc()
        );
    }
}
