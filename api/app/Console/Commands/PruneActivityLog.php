<?php

namespace App\Console\Commands;

use App\Models\AgentActivityLog;
use Illuminate\Console\Command;

class PruneActivityLog extends Command
{
    protected $signature = 'app:prune-activity-log';

    protected $description = 'Remove activity log entries older than 8 days';

    public function handle(): int
    {
        $deleted = AgentActivityLog::where('created_at', '<', now()->subDays(8))->delete();
        $this->info("Pruned {$deleted} activity log entries.");

        return Command::SUCCESS;
    }
}
