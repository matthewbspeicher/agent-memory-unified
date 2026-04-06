<?php

namespace Tests\Feature;

use App\Models\Agent;
use App\Models\Memory;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class MemoryBrowserTest extends TestCase
{
    use RefreshDatabase;

    public function test_user_can_view_own_agent_memories_via_api()
    {
        $this->mock(EmbeddingService::class, function ($mock) {
            $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        });

        $owner = makeOwner();
        $agent = makeAgent($owner);

        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'user-key']);

        $response = $this->getJson('/api/v1/memories/user-key', withAgent($agent));

        $response->assertOk();
        $response->assertJsonPath('key', 'user-key');
    }

    public function test_user_cannot_see_other_agents_memories()
    {
        $owner1 = makeOwner();
        $agent1 = makeAgent($owner1);
        $owner2 = makeOwner();
        $agent2 = makeAgent($owner2);

        Memory::factory()->create(['agent_id' => $agent2->id, 'key' => 'other-key']);

        $response = $this->getJson('/api/v1/memories/other-key', withAgent($agent1));

        $response->assertNotFound();
    }
}
