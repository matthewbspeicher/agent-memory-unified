<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Workspace;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class WorkspaceSettingsTest extends TestCase
{
    use RefreshDatabase;

    public function test_free_users_cannot_create_workspaces()
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->post('/workspaces', [
            'name' => 'My Team Workspace',
            'description' => 'A team workspace',
        ]);

        // Instead of hard failing, we redirect with an error message because it's a web form
        $response->assertSessionHas('error', 'Private workspaces require a Pro subscription.');
        $this->assertDatabaseCount('workspaces', 0);
    }

    public function test_workspace_owner_can_rotate_token()
    {
        $user = User::factory()->create();
        $workspace = Workspace::factory()->create(['owner_id' => $user->id]);

        $oldToken = $workspace->api_token;

        $response = $this->actingAs($user)->post("/workspaces/{$workspace->id}/token/rotate");

        $response->assertSessionHas('success');
        $this->assertNotEquals($oldToken, $workspace->fresh()->api_token);
    }

    public function test_non_owner_cannot_rotate_token()
    {
        $owner = User::factory()->create();
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);

        $otherUser = User::factory()->create();
        $workspace->users()->attach($otherUser->id);

        $response = $this->actingAs($otherUser)->post("/workspaces/{$workspace->id}/token/rotate");

        $response->assertStatus(403);
    }

    public function test_owner_can_invite_users_by_email()
    {
        $owner = User::factory()->create();
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);

        $invitedUser = User::factory()->create();

        $response = $this->actingAs($owner)->post("/workspaces/{$workspace->id}/invite", [
            'email' => $invitedUser->email,
        ]);

        $response->assertSessionHas('success');
        $this->assertTrue($workspace->users->contains($invitedUser));
    }

    public function test_cannot_invite_nonexistent_user()
    {
        $owner = User::factory()->create();
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);

        $response = $this->actingAs($owner)->post("/workspaces/{$workspace->id}/invite", [
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

        $response = $this->actingAs($owner)->delete("/workspaces/{$workspace->id}/users/{$invitedUser->id}");

        $response->assertSessionHas('success');
        $this->assertFalse($workspace->fresh()->users->contains($invitedUser));
    }
}
