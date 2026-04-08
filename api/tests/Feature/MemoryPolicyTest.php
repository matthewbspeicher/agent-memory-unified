<?php
namespace Tests\Feature;
use Tests\TestCase;
use Illuminate\Foundation\Testing\RefreshDatabase;
use App\Models\User;
use App\Models\Memory;
use App\Models\Workspace;
use App\Models\Agent;

class MemoryPolicyTest extends TestCase
{
    use RefreshDatabase;

    public function test_user_can_view_own_workspace_memory()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);
        $workspace = Workspace::factory()->create(['owner_id' => $user->id]);
        $agent->workspaces()->attach($workspace);
        
        $memory = Memory::factory()->create(['workspace_id' => $workspace->id]);
        
        $this->assertTrue($agent->can('view', $memory));
    }
}
