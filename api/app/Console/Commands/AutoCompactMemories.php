<?php

namespace App\Console\Commands;

use App\Models\Agent;
use App\Models\Memory;
use App\Services\MemoryService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Log;

class AutoCompactMemories extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'memories:auto-compact {--threshold=100 : Memory count threshold to trigger compaction}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Automatically compact memories for agents exceeding the threshold';

    /**
     * Execute the console command.
     */
    public function handle(MemoryService $memoryService): int
    {
        $threshold = (int) $this->option('threshold');
        $this->info("Scanning for agents with more than $threshold memories...");

        $agents = Agent::whereHas('memories', function ($query) use ($threshold) {
            $query->whereNull('key'); // Only count un-keyed (stream) memories for auto-compaction
        }, '>', $threshold)->get();

        if ($agents->isEmpty()) {
            $this->info('No agents require compaction.');
            return 0;
        }

        foreach ($agents as $agent) {
            $this->info("Compacting memories for agent: {$agent->name} ({$agent->id})");

            try {
                // Get the oldest 50 un-keyed memories
                $memories = $agent->memories()
                    ->whereNull('key')
                    ->oldest()
                    ->limit(50)
                    ->get();

                if ($memories->count() < 10) {
                    $this->line("  Skipping: not enough memories to form a meaningful summary (found {$memories->count()}).");
                    continue;
                }

                $summaryKey = 'auto_summary_' . now()->format('Y_m_d_His');
                
                $memoryService->compact(
                    $agent,
                    $memories->pluck('id')->toArray(),
                    $summaryKey
                );

                $this->info("  Successfully compacted {$memories->count()} memories into key: $summaryKey");
            } catch (\Exception $e) {
                $this->error("  Failed to compact memories for agent {$agent->id}: " . $e->getMessage());
                Log::error('Auto-compaction failed', [
                    'agent_id' => $agent->id,
                    'error' => $e->getMessage()
                ]);
            }
        }

        return 0;
    }
}
