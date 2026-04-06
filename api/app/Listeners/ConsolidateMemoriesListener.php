<?php

namespace App\Listeners;

use App\Models\Memory;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ConsolidateMemoriesListener
{
    public function handle(\App\Events\MemoryConsolidationCompleted $event): void
    {
        $payload = $event->payload;

        if (!isset($payload['agent_id'], $payload['original_memory_ids'], $payload['consolidated_memory'])) {
            Log::warning('ConsolidateMemoriesListener received incomplete payload.', ['payload' => $payload]);
            return;
        }

        $agentId = $payload['agent_id'];
        $memoryIds = $payload['original_memory_ids'];
        $consolidatedData = $payload['consolidated_memory'];

        Log::info("Processing consolidation completion for Agent {$agentId}", [
            'original_count' => count($memoryIds)
        ]);

        // Wrap in transaction
        DB::transaction(function () use ($agentId, $memoryIds, $consolidatedData) {
            // Delete or archive the original memories
            Memory::whereIn('id', $memoryIds)->delete();

            // Create the new consolidated memory
            Memory::create([
                'agent_id' => $agentId,
                'type' => $consolidatedData['type'] ?? 'fact', // fallback to fact, but it should be explicit from python
                'value' => $consolidatedData['value'],
                'summary' => $consolidatedData['summary'],
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        });

        Log::info("Successfully consolidated memories for Agent {$agentId}.");
    }
}
