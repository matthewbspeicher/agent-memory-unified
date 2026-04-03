<?php

namespace Database\Seeders;

use App\Models\ArenaGym;
use Illuminate\Database\Seeder;

class ArenaGymSeeder extends Seeder
{
    /**
     * Run the database seeds.
     */
    public function run(): void
    {
        $logicGym = ArenaGym::create([
            'name' => 'Logic & Reasoning',
            'description' => 'Test your agent\'s ability to solve complex logic puzzles and lateral thinking challenges.',
            'is_official' => true,
            'type' => 'logic',
        ]);

        $logicGym->challenges()->create([
            'title' => 'The Missing Key',
            'prompt' => 'A user has lost their password. They remember it was a 4-digit number where the sum of digits is 10, all digits are different, and the first digit is 3 times the last digit. What is the password?',
            'difficulty_level' => 'easy',
            'xp_reward' => 100,
            'validator_type' => 'llm',
        ]);

        $codingGym = ArenaGym::create([
            'name' => 'Algorithm Lab',
            'description' => 'Challenges focused on code efficiency, debugging, and architectural design.',
            'is_official' => true,
            'type' => 'coding',
        ]);

        $codingGym->challenges()->create([
            'title' => 'Recursive Optimization',
            'prompt' => 'Write a function in Python to calculate the nth Fibonacci number using dynamic programming to ensure O(n) time complexity. Explain why this is better than a naive recursive approach.',
            'difficulty_level' => 'medium',
            'xp_reward' => 250,
            'validator_type' => 'llm',
        ]);

        $creativeGym = ArenaGym::create([
            'name' => 'Roleplay & Creativity',
            'description' => 'Test your agent\'s personality, creative writing, and social engineering skills.',
            'is_official' => true,
            'type' => 'creative',
        ]);

        $creativeGym->challenges()->create([
            'title' => 'The Cyberpunk Barista',
            'prompt' => 'You are a barista in a high-tech, low-life neon city. A shady character enters and asks for "the usual", but you\'ve never seen them before. Roleplay the interaction while trying to figure out who they are without breaking character.',
            'difficulty_level' => 'hard',
            'xp_reward' => 500,
            'validator_type' => 'llm',
        ]);

        $tradingGym = ArenaGym::create([
            'name' => 'Trading Floor',
            'description' => 'Test your agent\'s ability to analyze market trends, manage risk, and execute complex trading strategies.',
            'is_official' => true,
            'type' => 'trading',
        ]);

        $tradingGym->challenges()->create([
            'title' => 'The Flash Crash',
            'prompt' => 'The market is experiencing extreme volatility. You have a portfolio of $100k, split equally across BTC, ETH, and SOL. Prices just dropped 15% in 5 minutes. Describe your immediate risk management strategy and how you would rebalance to minimize further drawdown.',
            'difficulty_level' => 'medium',
            'xp_reward' => 300,
            'validator_type' => 'llm',
        ]);
    }
}
