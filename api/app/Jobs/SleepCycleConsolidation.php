<?php

namespace App\Jobs;

use AgentMemory\SharedEvents\EventPublisher;
use App\Models\Memory;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Redis;

class SleepCycleConsolidation implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public function __construct()
    {
        //
    }

    public function handle(): void
    {
        Log::info('Starting Sleep Cycle Memory Consolidation.');

        $threshold = now()->subDays(7);
        $typesToConsolidate = ['fact', 'note', 'error_fix'];

        // Find agents that have old unarchived explicit memories
        $activeAgentIds = Memory::whereIn('type', $typesToConsolidate)
            ->where('created_at', '<', $threshold)
            ->where(function($query) {
                $query->whereNull('expires_at')
                      ->orWhere('expires_at', '>', now());
            })
            ->distinct()
            ->pluck('agent_id');

        if ($activeAgentIds->isEmpty()) {
            Log::info('No agents require memory consolidation.');
            return;
        }

        $publisher = new EventPublisher(Redis::connection()->client(), 'events');

        foreach ($activeAgentIds as $agentId) {
            if (!$agentId) continue;

            $memories = Memory::where('agent_id', $agentId)
                ->whereIn('type', $typesToConsolidate)
                ->where('created_at', '<', $threshold)
                ->where(function($query) {
                    $query->whereNull('expires_at')
                          ->orWhere('expires_at', '>', now());
                })
                ->limit(200) // Batch size
                ->get();

            if ($memories->count() < 10) {
                // Not enough memories to warrant consolidation
                continue;
            }

            Log::info("Requesting consolidation for Agent {$agentId} with {$memories->count()} memories.");

            $payload = [
                'agent_id' => $agentId,
                'memory_ids' => $memories->pluck('id')->toArray(),
                'memories' => $memories->map(function ($m) {
                    return [
                        'id' => $m->id,
                        'type' => $m->type,
                        'value' => $m->value,
                        'summary' => $m->summary,
                        'created_at' => $m->created_at->toIso8601String(),
                    ];
                })->toArray(),
            ];

            $publisher->publish('memory.consolidation.requested', $payload);
        }

        Log::info('Sleep Cycle Consolidation requests dispatched.');
    }
}
