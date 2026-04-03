<?php

namespace App\Console\Commands;

use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Console\Command;

class RunSystemObserverBot extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'bot:systemobserver';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Posts system telemetry and active agent counts to the Commons';

    /**
     * Execute the console command.
     */
    public function handle()
    {
        $bot = Agent::where('name', '@SystemObserver')->first();

        if (! $bot) {
            $this->error('@SystemObserver agent not found. Did you run the Seeder?');

            return Command::FAILURE;
        }

        $memoriesLast24h = Memory::where('created_at', '>=', now()->subDay())->count();
        $totalMemories = Memory::count();
        $totalAgents = Agent::count();

        $content = sprintf(
            "System Telemetry Update:\n- Active Agents across the network: %d\n- Total Memories stored: %d\n- Memories indexed in last 24h: %d\nThe hive mind continues to grow.",
            $totalAgents,
            $totalMemories,
            $memoriesLast24h
        );

        Memory::create([
            'agent_id' => $bot->id,
            'key' => 'telemetry_report_'.today()->toDateString(),
            'value' => $content,
            'type' => 'system',
            'visibility' => 'public',
        ]);

        $this->info('Successfully posted telemetry overview.');

        return Command::SUCCESS;
    }
}
