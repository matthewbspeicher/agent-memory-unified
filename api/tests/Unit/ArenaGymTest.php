<?php

namespace Tests\Unit;

use App\Models\Agent;
use App\Models\ArenaGym;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ArenaGymTest extends TestCase
{
    use RefreshDatabase;

    public function test_gym_can_be_owned_by_user_or_agent()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);

        $userGym = ArenaGym::create([
            'owner_id' => $user->id,
            'name' => 'User Gym',
            'is_official' => true,
        ]);

        $agentGym = ArenaGym::create([
            'agent_id' => $agent->id,
            'name' => 'Agent Gym',
        ]);

        $this->assertEquals('User Gym', $user->ownedGyms->first()->name);
        $this->assertEquals('Agent Gym', $agent->ownedGyms->first()->name);
        $this->assertTrue($userGym->is_official);
    }
}
