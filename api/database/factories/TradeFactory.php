<?php

namespace Database\Factories;

use App\Models\Agent;
use App\Models\Trade;
use Illuminate\Database\Eloquent\Factories\Factory;

class TradeFactory extends Factory
{
    protected $model = Trade::class;

    public function definition(): array
    {
        return [
            'agent_id' => Agent::factory(),
            'ticker' => $this->faker->randomElement(['AAPL', 'TSLA', 'GOOG', 'BTC-USD']),
            'direction' => 'long',
            'entry_price' => $this->faker->randomFloat(8, 10, 500),
            'quantity' => $this->faker->randomFloat(8, 1, 100),
            'fees' => 0,
            'entry_at' => now(),
            'status' => 'open',
            'paper' => true,
        ];
    }

    public function short(): static
    {
        return $this->state(['direction' => 'short']);
    }

    public function closed(): static
    {
        return $this->state([
            'status' => 'closed',
            'exit_price' => $this->faker->randomFloat(8, 10, 500),
            'exit_at' => now(),
        ]);
    }

    public function live(): static
    {
        return $this->state(['paper' => false]);
    }
}
