<?php

namespace App\Console\Commands;

use App\Models\Memory;
use Illuminate\Console\Command;

class PruneExpiredMemories extends Command
{
    protected $signature = 'memories:prune';

    protected $description = 'Delete memories that have passed their expiration date';

    public function handle(): int
    {
        $count = Memory::query()
            ->whereNotNull('expires_at')
            ->where('expires_at', '<=', now())
            ->delete();

        $this->info("Pruned {$count} expired memories.");

        return self::SUCCESS;
    }
}
