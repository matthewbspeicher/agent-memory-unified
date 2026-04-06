<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Workspace;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class WorkspaceSettingsTest extends TestCase
{
    use RefreshDatabase;

    public function test_authenticated_user_can_create_workspaces()
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)
            ->withSession(['_token' => 'test-token'])
            ->post('/workspaces', [
                '_token' => 'test-token',
                'name' => 'My Team Workspace',
                'description' => 'A team workspace',
            ]);

        // User is always "Pro" in the simplified model, so workspace creation succeeds
        $response->assertSessionHas('success', 'Workspace created!');
        $this->assertDatabaseCount('workspaces', 1);
    }

    public function test_workspace_owner_can_rotate_token()
    {
        $user = User::factory()->create();
        $workspace = Workspace::factory()->create(['owner_id' => $user->id]);

        $oldHash = $workspace->api_token_hash;

        $response = $this->actingAs($user)
            ->withSession(['_token' => 'test-token'])
            ->post("/workspaces/{$workspace->id}/token/rotate", [
                '_token' => 'test-token',
            ]);

        $response->assertSessionHas('success');
        $this->assertNotEquals($oldHash, $workspace->fresh()->api_token_hash);
    }

    public function test_non_owner_cannot_rotate_token()
    {
        $owner = User::factory()->create();
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);

        $otherUser = User::factory()->create();
        $workspace->users()->attach($otherUser->id);

        $response = $this->actingAs($otherUser)
            ->withSession(['_token' => 'test-token'])
            ->post("/workspaces/{$workspace->id}/token/rotate", [
                '_token' => 'test-token',
            ]);

        $response->assertStatus(403);
    }

    public function test_owner_can_invite_users_by_email()
    {
        $owner = User::factory()->create();
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);

        $invitedUser = User::factory()->create();

        $response = $this->actingAs($owner)
            ->withSession(['_token' => 'test-token'])
            ->post("/workspaces/{$workspace->id}/invite", [
                '_token' => 'test-token',
                'email' => $invitedUser->email,
            ]);

        $response->assertSessionHas('success');
        $this->assertTrue($workspace->fresh()->users->contains($invitedUser));
    }

    public function test_cannot_invite_nonexistent_user()
    {
        $owner = User::factory()->create();
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);

        $response = $this->actingAs($owner)
            ->withSession(['_token' => 'test-token'])
            ->post("/workspaces/{$workspace->id}/invite", [
                '_token' => 'test-token',
                'email' => 'doesnotexist@example.com',
            ]);

        $response->assertSessionHas('error', 'User with that email not found.');
    }

    public function test_owner_can_remove_users()
    {
        $owner = User::factory()->create();
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);

        $invitedUser = User::factory()->create();
        $workspace->users()->attach($invitedUser->id);

        $response = $this->actingAs($owner)
            ->withSession(['_token' => 'test-token'])
            ->delete("/workspaces/{$workspace->id}/users/{$invitedUser->id}", [
                '_token' => 'test-token',
            ]);

        $response->assertSessionHas('success');
        $this->assertFalse($workspace->fresh()->users->contains($invitedUser));
    }
}
