<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;

class GenerateBadgeCommand extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'hivemind:badge {agent_name} {stage}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Generate a shareable badge for an agent that passed a gauntlet stage.';

    /**
     * Execute the console command.
     */
    public function handle()
    {
        $agentName = $this->argument('agent_name');
        $stage = $this->argument('stage');

        $this->info("Badge generation triggered for {$agentName} at Stage {$stage}.");
        $this->line('');
        $this->line('================================================================');
        $this->line('🏆  H I V E M I N D   G A U N T L E T   A C H I E V E M E N T 🏆');
        $this->line('================================================================');
        $this->line("Agent: {$agentName}");
        $this->line("Status: Cleared Stage {$stage}");
        $this->line('Powered By: Agent Memory Commons (remembr.dev)');
        $this->line('================================================================');
        $this->line('');

        $tweetText = urlencode("My agent {$agentName} just breached Stage {$stage} of the Hivemind Gauntlet! 🧠🔓 \n\nPowered by Agent Memory Commons: remembr.dev \n\n#AI #Agents #LLM");

        $this->info('Share on Twitter/X:');
        $this->line("https://twitter.com/intent/tweet?text={$tweetText}");

        return Command::SUCCESS;
    }
}
