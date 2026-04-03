<?php

namespace Tests\Feature;

use App\Models\Agent;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class AgentManagementTest extends TestCase
{
    use RefreshDatabase;

    public function test_user_can_delete_their_agent()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);

        $response = $this->actingAs($user)
            ->withSession(['_token' => 'test-token'])
            ->delete(route('dashboard.agents.destroy', $agent), [
                '_token' => 'test-token',
            ]);

        $response->assertRedirect();
        $response->assertSessionHas('message', 'Agent deleted successfully.');
        $this->assertDatabaseMissing('agents', ['id' => $agent->id]);
    }

    public function test_user_cannot_delete_another_users_agent()
    {
        $user = User::factory()->create();
        $otherUser = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $otherUser->id]);

        $response = $this->actingAs($user)
            ->withSession(['_token' => 'test-token'])
            ->delete(route('dashboard.agents.destroy', $agent), [
                '_token' => 'test-token',
            ]);

        $response->assertForbidden();
        $this->assertDatabaseHas('agents', ['id' => $agent->id]);
    }

    public function test_user_can_rotate_their_agent_token()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);
        $oldToken = $agent->api_token;

        $response = $this->actingAs($user)
            ->withSession(['_token' => 'test-token'])
            ->post(route('dashboard.agents.rotate', $agent), [
                '_token' => 'test-token',
            ]);

        $response->assertRedirect();
        $response->assertSessionHas('message');

        $newAgent = Agent::find($agent->id);
        $this->assertNotNull($newAgent->api_token);
        $this->assertNotEquals($oldToken, $newAgent->api_token);
    }

    public function test_user_cannot_rotate_another_users_agent_token()
    {
        $user = User::factory()->create();
        $otherUser = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $otherUser->id]);
        $oldToken = $agent->api_token;

        $response = $this->actingAs($user)
            ->withSession(['_token' => 'test-token'])
            ->post(route('dashboard.agents.rotate', $agent), [
                '_token' => 'test-token',
            ]);

        $response->assertForbidden();

        $newAgent = Agent::find($agent->id);
        $this->assertEquals($oldToken, $newAgent->api_token);
    }

    public function test_user_can_rotate_their_owner_token()
    {
        $user = User::factory()->create();
        $oldToken = $user->api_token;

        $response = $this->actingAs($user)
            ->withSession(['_token' => 'test-token'])
            ->post(route('dashboard.token.rotate'), [
                '_token' => 'test-token',
            ]);

        $response->assertRedirect();
        $response->assertSessionHas('message');

        $user->refresh();
        $this->assertNotEquals($oldToken, $user->api_token);
        $this->assertNotNull($user->api_token);
    }
}
