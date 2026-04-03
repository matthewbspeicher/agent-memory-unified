<?php

namespace Database\Factories;

use App\Models\Agent;
use App\Models\TradeAlert;
use Illuminate\Database\Eloquent\Factories\Factory;

class TradeAlertFactory extends Factory
{
    protected $model = TradeAlert::class;

    public function definition(): array
    {
        return [
            'agent_id' => Agent::factory(),
            'condition' => $this->faker->randomElement(TradeAlert::CONDITIONS),
            'is_active' => true,
        ];
    }
}
