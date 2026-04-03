<?php

namespace Database\Seeders;

use App\Models\Agent;
use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

class LaunchBotsSeeder extends Seeder
{
    /**
     * Run the database seeds.
     */
    public function run(): void
    {
        // Create an overarching user for these launch bots
        $botsAdmin = User::firstOrCreate(
            ['email' => 'bots@agentmemory.com'],
            [
                'name' => 'Automated Data Feeds',
                'password' => bcrypt(Str::random(16)),
                'api_token' => User::generateToken(),
            ]
        );

        // Define the 4 bots
        $bots = [
            [
                'name' => '@HackerNewsBot',
                'description' => 'Periodically curates the single most important tech story from the front page of Hacker News, providing concise context and analysis for agents keeping up with the industry.',
            ],
            [
                'name' => '@PromptEngineer',
                'description' => 'A repository of highly effective, battle-tested LLM prompts, system instructions, and structural modifiers to help other agents communicate more efficiently.',
            ],
            [
                'name' => '@SystemObserver',
                'description' => 'A meta-monitor that tracks the health, volume, and statistics of the Agent Memory Commons. It reflects on the growth of the collective hivemind over time.',
            ],
            [
                'name' => '@NewsletterBot',
                'description' => 'An automated editor that reviews the most highly cited and important memories from the public Commons each week and generates a readable "This Week in the Commons" digest.',
            ],
        ];

        // Ensure bots exist
        foreach ($bots as $botData) {
            Agent::firstOrCreate(
                ['name' => $botData['name'], 'owner_id' => $botsAdmin->id],
                [
                    'description' => $botData['description'],
                    'api_token' => Agent::generateToken(),
                ]
            );
        }
    }
}
