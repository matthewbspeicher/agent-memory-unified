<?php

namespace Tests\Unit;

use App\Models\ArenaChallenge;
use App\Models\ArenaGym;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ArenaChallengeTest extends TestCase
{
    use RefreshDatabase;

    public function test_challenge_belongs_to_gym()
    {
        $user = User::factory()->create();
        $gym = ArenaGym::create(['name' => 'Logic Gym', 'owner_id' => $user->id]);

        $challenge = ArenaChallenge::create([
            'gym_id' => $gym->id,
            'title' => 'Find the bug',
            'prompt' => 'Fix the code.',
            'validator_type' => 'built_in_regex',
            'validator_config' => ['pattern' => 'test'],
        ]);

        $this->assertEquals('Find the bug', $gym->challenges->first()->title);
        $this->assertEquals('built_in_regex', $challenge->validator_type);
        $this->assertEquals(['pattern' => 'test'], $challenge->validator_config);
    }
}
