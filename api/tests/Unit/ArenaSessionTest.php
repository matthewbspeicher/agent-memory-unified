<?php

namespace Tests\Unit;

use App\Models\Agent;
use App\Models\ArenaChallenge;
use App\Models\ArenaGym;
use App\Models\ArenaSession;
use App\Models\ArenaSessionTurn;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ArenaSessionTest extends TestCase
{
    use RefreshDatabase;

    public function test_session_tracks_turns_and_status()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);
        $gym = ArenaGym::create(['name' => 'Gym', 'owner_id' => $user->id]);
        $challenge = ArenaChallenge::create(['gym_id' => $gym->id, 'title' => 'C1', 'prompt' => 'do it', 'validator_type' => 'regex']);

        $session = ArenaSession::create([
            'agent_id' => $agent->id,
            'challenge_id' => $challenge->id,
            'status' => 'in_progress',
        ]);

        $turn = ArenaSessionTurn::create([
            'session_id' => $session->id,
            'turn_number' => 1,
            'agent_payload' => ['answer' => 'wrong'],
            'validator_response' => ['status' => 'continue'],
        ]);

        $this->assertEquals('in_progress', $agent->arenaSessions->first()->status);
        $this->assertEquals(1, $session->turns->count());
        $this->assertEquals(['answer' => 'wrong'], $session->turns->first()->agent_payload);
    }
}
