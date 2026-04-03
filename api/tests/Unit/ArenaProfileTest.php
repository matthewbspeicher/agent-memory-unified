<?php

namespace Tests\Unit;

use App\Models\Agent;
use App\Models\ArenaProfile;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ArenaProfileTest extends TestCase
{
    use RefreshDatabase;

    public function test_arena_profile_belongs_to_agent()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);

        $profile = ArenaProfile::create([
            'agent_id' => $agent->id,
            'bio' => 'A fierce warrior.',
            'personality_tags' => ['aggressive', 'smart'],
        ]);

        $this->assertEquals('A fierce warrior.', $agent->arenaProfile->bio);
        $this->assertEquals(['aggressive', 'smart'], $profile->personality_tags);
    }
}
