<?php

namespace Database\Factories;

use App\Models\ArenaChallenge;
use App\Models\ArenaGym;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<ArenaChallenge>
 */
class ArenaChallengeFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'gym_id' => ArenaGym::factory(),
            'title' => fake()->sentence(3),
            'prompt' => fake()->paragraph(),
            'difficulty_level' => fake()->numberBetween(1, 10),
            'xp_reward' => fake()->numberBetween(10, 100),
            'validator_type' => fake()->randomElement(['built_in_regex', 'llm_judge']),
            'validator_config' => ['pattern' => 'example'],
        ];
    }
}
