<?php

namespace Tests\Feature;

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class MemoryBrowserTest extends TestCase
{
    use RefreshDatabase;

    public function test_user_can_view_memory_browser()
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)
            ->get(route('memories.index'));

        $response->assertOk();
    }

    public function test_user_sees_only_own_agents_memories()
    {
        $user = User::factory()->create();
        $otherUser = User::factory()->create();

        $userAgent = Agent::factory()->create(['owner_id' => $user->id]);
        $otherAgent = Agent::factory()->create(['owner_id' => $otherUser->id]);

        $userMemory = Memory::factory()->create(['agent_id' => $userAgent->id, 'key' => 'user-key']);
        $otherMemory = Memory::factory()->create(['agent_id' => $otherAgent->id, 'key' => 'other-key']);

        $response = $this->actingAs($user)
            ->get(route('memories.index'));

        $response->assertOk();
        $response->assertSee('user-key');
        $response->assertDontSee('other-key');
    }
}
