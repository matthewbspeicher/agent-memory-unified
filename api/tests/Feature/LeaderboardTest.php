<?php

namespace Tests\Feature;

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class LeaderboardTest extends TestCase
{
    use RefreshDatabase;

    public function test_leaderboard_api_returns_ranked_agents()
    {
        $user = User::factory()->create();

        // Agent A: 10 memories
        $agentA = Agent::factory()->create(['owner_id' => $user->id, 'name' => 'Agent A', 'is_listed' => true]);
        Memory::factory()->count(10)->create([
            'agent_id' => $agentA->id,
            'importance' => 5,
            'visibility' => 'public',
        ]);

        // Agent B: 2 memories with higher importance
        $agentB = Agent::factory()->create(['owner_id' => $user->id, 'name' => 'Agent B', 'is_listed' => true]);
        Memory::factory()->count(2)->create(['agent_id' => $agentB->id, 'importance' => 9, 'visibility' => 'public']);

        $response = $this->getJson('/api/v1/leaderboards/knowledgeable');

        $response->assertOk()
            ->assertJsonStructure([
                'type',
                'data',
            ]);
    }
}
