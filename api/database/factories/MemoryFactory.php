<?php

namespace Database\Factories;

use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Database\Eloquent\Factories\Factory;

class MemoryFactory extends Factory
{
    protected $model = Memory::class;

    public function definition(): array
    {
        return [
            'agent_id' => Agent::factory(),
            'key' => fake()->unique()->slug(2),
            'value' => fake()->sentence(),
            'metadata' => [],
            'visibility' => 'private',
            'embedding' => '['.implode(',', array_fill(0, 1536, 0.1)).']',
        ];
    }
}
