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
        $oldHash = $agent->token_hash;

        $response = $this->actingAs($user)
            ->withSession(['_token' => 'test-token'])
            ->post(route('dashboard.agents.rotate', $agent), [
                '_token' => 'test-token',
            ]);

        $response->assertRedirect();
        $response->assertSessionHas('message');

        $newAgent = Agent::find($agent->id);
        $this->assertNotNull($newAgent->token_hash);
        $this->assertNotEquals($oldHash, $newAgent->token_hash);
    }

    public function test_user_cannot_rotate_another_users_agent_token()
    {
        $user = User::factory()->create();
        $otherUser = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $otherUser->id]);
        $oldHash = $agent->token_hash;

        $response = $this->actingAs($user)
            ->withSession(['_token' => 'test-token'])
            ->post(route('dashboard.agents.rotate', $agent), [
                '_token' => 'test-token',
            ]);

        $response->assertForbidden();

        $newAgent = Agent::find($agent->id);
        $this->assertEquals($oldHash, $newAgent->token_hash);
    }

    public function test_user_can_rotate_their_owner_token()
    {
        $user = User::factory()->create();
        $oldHash = $user->api_token_hash;

        $response = $this->actingAs($user)
            ->withSession(['_token' => 'test-token'])
            ->post(route('dashboard.token.rotate'), [
                '_token' => 'test-token',
            ]);

        $response->assertRedirect();
        $response->assertSessionHas('message');

        $user->refresh();
        $this->assertNotEquals($oldHash, $user->api_token_hash);
        $this->assertNotNull($user->api_token_hash);
    }
}
