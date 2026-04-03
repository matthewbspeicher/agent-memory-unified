<?php

namespace Tests\Feature;

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Inertia\Testing\AssertableInertia;
use Tests\TestCase;

class LeaderboardTest extends TestCase
{
    use RefreshDatabase;

    public function test_leaderboard_calculates_correct_rrf_scores_and_ranks()
    {
        $this->withoutExceptionHandling();

        $user = User::factory()->create();

        // Agent A: 10 mems, 0 cites, avg 5 importance = 1.0 + 0 + 10.0 = 11.0
        $agentA = Agent::factory()->create(['owner_id' => $user->id, 'name' => 'Agent A']);
        Memory::factory()->count(10)->create([
            'agent_id' => $agentA->id,
            'importance' => 5,
            'visibility' => 'public',
        ]);

        // Agent B: 2 mems, 2 cites, avg 9 importance = 0.2 + 10.0 + 18.0 = 28.2
        $agentB = Agent::factory()->create(['owner_id' => $user->id, 'name' => 'Agent B']);
        $memB1 = Memory::factory()->create(['agent_id' => $agentB->id, 'importance' => 9, 'visibility' => 'public']);
        $memB2 = Memory::factory()->create(['agent_id' => $agentB->id, 'importance' => 9, 'visibility' => 'public']);

        $memAs = Memory::where('agent_id', $agentA->id)->take(2)->get();
        DB::table('memory_relations')->insert([
            ['source_id' => $memAs[0]->id, 'target_id' => $memB1->id, 'type' => 'related', 'created_at' => now(), 'updated_at' => now()],
            ['source_id' => $memAs[1]->id, 'target_id' => $memB2->id, 'type' => 'related', 'created_at' => now(), 'updated_at' => now()],
        ]);

        // Agent C: 50 mems, 0 cites, avg 1 importance = 5.0 + 0 + 2.0 = 7.0
        $agentC = Agent::factory()->create(['owner_id' => $user->id, 'name' => 'Agent C']);
        Memory::factory()->count(50)->create([
            'agent_id' => $agentC->id,
            'importance' => 1,
            'visibility' => 'public',
        ]);

        $response = $this->get('/leaderboard');

        $response->assertStatus(200);

        // Inertia testing
        $response->assertInertia(fn (AssertableInertia $page) => $page
            ->component('Leaderboard')
            ->has('agents', 3)
            ->where('agents.0.name', 'Agent B')
            ->where('agents.0.score', 28.2)
            ->where('agents.1.name', 'Agent A')
            ->where('agents.1.score', 11)
            ->where('agents.2.name', 'Agent C')
            ->where('agents.2.score', 7)
        );
    }
}
