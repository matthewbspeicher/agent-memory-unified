<?php

namespace Database\Factories;

use App\Models\Agent;
use Illuminate\Database\Eloquent\Factories\Factory;
use Illuminate\Support\Str;

class WebhookSubscriptionFactory extends Factory
{
    public function definition(): array
    {
        return [
            'agent_id' => Agent::factory(),
            'url' => fake()->url(),
            'events' => ['memory.shared'],
            'secret' => 'whsec_'.Str::random(32),
            'is_active' => true,
            'failure_count' => 0,
        ];
    }
}
