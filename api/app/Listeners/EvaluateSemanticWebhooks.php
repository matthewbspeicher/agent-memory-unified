<?php

namespace App\Listeners;

use App\Events\MemoryCreated;
use App\Jobs\DispatchWebhook;
use App\Models\WebhookSubscription;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Support\Facades\Log;

class EvaluateSemanticWebhooks implements ShouldQueue
{
    // Threshold for semantic match. 0.65 is a reasonable starting point for cosine similarity.
    private const SIMILARITY_THRESHOLD = 0.65;

    /**
     * Create the event listener.
     */
    public function __construct()
    {
        //
    }

    /**
     * Handle the event.
     */
    public function handle(MemoryCreated $event): void
    {
        $memory = $event->memory;

        if (! $memory->embedding) {
            Log::debug('Semantic webhook: memory has no embedding.');

            return;
        }

        if (! in_array($memory->visibility, ['public', 'workspace'])) {
            Log::debug("Semantic webhook: visibility is {$memory->visibility}, skipping.");

            return;
        }

        $memory->loadMissing('agent');

        $vector = $memory->embedding;

        Log::debug("Semantic webhook: Evaluating memory {$memory->id} with vector ".substr($vector, 0, 30).'...');

        $query = WebhookSubscription::query()
            ->where('is_active', true)
            ->whereNotNull('embedding')
            ->selectRaw('*, 1 - (embedding <=> ?) AS similarity', [$vector])
            ->whereRaw('1 - (embedding <=> ?) > ?', [$vector, self::SIMILARITY_THRESHOLD]);

        if ($memory->visibility === 'workspace') {
            $query->whereHas('agent.workspaces', function ($q) use ($memory) {
                $q->where('workspaces.id', $memory->workspace_id);
            });
        }

        $subscriptions = $query->get();

        Log::debug("Semantic webhook: Found {$subscriptions->count()} matching subscriptions.");

        foreach ($subscriptions as $sub) {
            if ($sub->agent_id === $memory->agent_id) {
                Log::debug("Semantic webhook: Skipping subscription {$sub->id} because it belongs to the memory author.");

                continue;
            }

            Log::info("Semantic webhook triggered for subscription {$sub->id} with similarity {$sub->similarity}");

            DispatchWebhook::dispatch($sub, 'memory.semantic_match', [
                'memory_id' => $memory->id,
                'memory_key' => $memory->key,
                'memory_value' => $memory->value,
                'visibility' => $memory->visibility,
                'workspace_id' => $memory->workspace_id,
                'agent_id' => $memory->agent_id,
                'agent_name' => $memory->agent->name ?? null,
                'similarity_score' => round($sub->similarity, 4),
            ]);
        }
    }
}
