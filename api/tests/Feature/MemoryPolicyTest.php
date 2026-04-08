<?php
namespace Tests\Feature;
use Tests\TestCase;
use Illuminate\Foundation\Testing\RefreshDatabase;
use App\Models\User;
use App\Models\Memory;
use App\Models\Workspace;

class MemoryPolicyTest extends TestCase
{
    use RefreshDatabase;

    public function test_user_can_view_own_workspace_memory()
    {
        $user = User::factory()->create();
        $workspace = Workspace::factory()->create(['user_id' => $user->id]);
        $memory = Memory::factory()->create(['workspace_id' => $workspace->id]);
        
        $this->assertTrue($user->can('view', $memory));
    }
}
