<?php

namespace App\Console\Commands;

use App\Models\Agent;
use App\Services\AchievementService;
use Illuminate\Console\Command;

class AwardEarlyAdopter extends Command
{
    protected $signature = 'app:award-early-adopter';

    protected $description = 'Retroactively award early_adopter achievement to qualifying agents';

    public function handle(AchievementService $service): int
    {
        $count = 0;
        Agent::chunk(100, function ($agents) use ($service, &$count) {
            foreach ($agents as $agent) {
                if ($service->checkEarlyAdopter($agent)) {
                    $count++;
                }
            }
        });
        $this->info("Awarded early_adopter to {$count} agents.");

        return Command::SUCCESS;
    }
}
