<?php

namespace Database\Factories;

use App\Models\ArenaGym;
use App\Models\User;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<ArenaGym>
 */
class ArenaGymFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'name' => fake()->company().' Gym',
            'description' => fake()->sentence(),
            'is_official' => fake()->boolean(20), // 20% chance of being official
            'owner_id' => User::factory(), // default to User owned
            // agent_id would be explicitly set when needed
        ];
    }
}
