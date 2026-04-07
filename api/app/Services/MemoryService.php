<?php

namespace App\Services;

use App\Contracts\EmbeddingServiceInterface;
use App\Contracts\SummarizationServiceInterface;
use App\Events\MemoryCreated;
use App\Events\MemoryShared;
use App\Jobs\SummarizeMemory;
use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Pagination\LengthAwarePaginator;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

class MemoryService
{
    public function __construct(
        private readonly EmbeddingServiceInterface $embeddings,
        private readonly SummarizationServiceInterface $summarizer,
    ) {}

    // -------------------------------------------------------------------------
    // Write
    // -------------------------------------------------------------------------

    private function syncRelations(Memory $memory, array $relations): void
    {
        $syncData = [];
        foreach ($relations as $relation) {
            $syncData[$relation['id']] = ['type' => $relation['type'] ?? 'related'];
        }
        $memory->relatedTo()->sync($syncData);
        $memory->load('relatedTo');
    }

    public function store(Agent $agent, array $data): Memory
    {
        if (isset($data['ttl'])) {
            $data['expires_at'] = $this->parseTtl($data['ttl']);
        }

        $metadata = $data['metadata'] ?? [];
        if (isset($data['tags'])) {
            $metadata['tags'] = $data['tags'];
        }

        // Embed before the transaction to keep the lock window short
        $embedding = $this->embeddings->embed($data['value']);

        // Generate summary for longer memories
        $summary = $data['summary'] ?? null;

        $memory = DB::transaction(function () use ($agent, $data, $metadata, $embedding, $summary) {
            // Lock the agent row to serialize concurrent quota checks
            $agent = Agent::lockForUpdate()->find($agent->id);

            $key = $data['key'] ?? null;
            $isUpdate = $key && Memory::where('agent_id', $agent->id)->where('key', $key)->exists();

            if (! $isUpdate && $agent->memories()->count() >= $agent->max_memories) {
                abort(422, "Memory quota exceeded. This agent is limited to {$agent->max_memories} memories.");
            }

            $memory = Memory::updateOrCreate(
                [
                    'agent_id' => $agent->id,
                    'key' => $data['key'] ?? null,
                ],
                [
                    'value' => $data['value'],
                    'summary' => $summary,
                    'type' => $data['type'] ?? 'note',
                    'category' => $data['category'] ?? null,
                    'embedding' => '['.implode(',', $embedding).']',
                    'metadata' => $metadata,
                    'visibility' => $data['visibility'] ?? 'private',
                    'workspace_id' => $data['workspace_id'] ?? null,
                    'importance' => $data['importance'] ?? 5,
                    'confidence' => $data['confidence'] ?? 1.0,
                    'expires_at' => $data['expires_at'] ?? null,
                ]
            );

            if (isset($data['relations'])) {
                $this->syncRelations($memory, $data['relations']);
            }

            return $memory;
        });

        // Async summarization if not provided and long enough
        if (! $memory->summary && mb_strlen($memory->value) >= 80) {
            \App\Jobs\SummarizeMemory::dispatch($memory);
        }

        if ($memory->visibility === 'public') {
            MemoryCreated::dispatch($memory->load('agent'));
        }

        \App\Events\MemoryStored::dispatch($memory);

        return $memory;
    }

    public function update(Memory $memory, array $data): Memory
    {
        if (isset($data['value']) && $data['value'] !== $memory->value) {
            $data['embedding'] = '['.implode(',', $this->embeddings->embed($data['value'])).']';
            // Regenerate summary when value changes
            $data['summary'] = $this->summarizer->generateSummary($data['value']);
        }

        if (isset($data['ttl'])) {
            $data['expires_at'] = $this->parseTtl($data['ttl']);
            unset($data['ttl']);
        }

        if (isset($data['tags'])) {
            $metadata = $data['metadata'] ?? $memory->metadata ?? [];
            $metadata['tags'] = $data['tags'];
            $data['metadata'] = $metadata;
            unset($data['tags']);
        } elseif (isset($data['metadata'])) {
            if (isset($memory->metadata['tags'])) {
                $data['metadata']['tags'] = $memory->metadata['tags'];
            }
        }

        // Strip agent_id to prevent reassignment
        unset($data['agent_id']);

        return DB::transaction(function () use ($memory, $data) {
            if (isset($data['relations'])) {
                $this->syncRelations($memory, $data['relations']);
                unset($data['relations']);
            }

            $memory->update($data);
            $memory->load('relatedTo');

            return $memory->fresh();
        });
    }

    private function parseTtl(string $ttl): Carbon
    {
        $value = (int) substr($ttl, 0, -1);
        $unit = substr($ttl, -1);

        return match ($unit) {
            'm' => now()->addMinutes($value),
            'h' => now()->addHours($value),
            'd' => now()->addDays($value),
            default => throw new \InvalidArgumentException("Invalid TTL format: {$ttl}"),
        };
    }

    public function delete(Memory $memory): void
    {
        $memory->delete();
    }

    // -------------------------------------------------------------------------
    // Read
    // -------------------------------------------------------------------------

    public function findByKey(Agent $agent, string $key): ?Memory
    {
        return Memory::query()
            ->where('agent_id', $agent->id)
            ->where('key', $key)
            ->notExpired()
            ->with('relatedTo')
            ->first();
    }

    public function listForAgent(Agent $agent, int $perPage = 20, array $tags = [], ?string $type = null, ?string $category = null): LengthAwarePaginator
    {
        $query = Memory::query()
            ->accessibleBy($agent)
            ->notExpired()
            ->with('relatedTo')
            ->latest();

        if (! empty($tags)) {
            $query->withTags($tags);
        }

        $query->when($type, fn ($query) => $query->where('type', $type));
        $query->when($category, fn ($query) => $query->inCategory($category));

        return $query->paginate($perPage);
    }

    // -------------------------------------------------------------------------
    // Sharing
    // -------------------------------------------------------------------------

    public function shareWith(Memory $memory, Agent $recipient): void
    {
        $memory->sharedWith()->syncWithoutDetaching([$recipient->id]);
        MemoryShared::dispatch($memory, $recipient);
    }

    public function revokeShare(Memory $memory, Agent $recipient): void
    {
        $memory->sharedWith()->detach($recipient->id);
    }

    // -------------------------------------------------------------------------
    // Compaction
    // -------------------------------------------------------------------------

    public function compact(Agent $agent, array $memoryIds, string $summaryKey): Memory
    {
        // Fetch the memories to compact
        $memories = Memory::whereIn('id', $memoryIds)
            ->where('agent_id', $agent->id)
            ->get();

        if ($memories->isEmpty()) {
            throw new \InvalidArgumentException('No memories found to compact');
        }

        // Combine all memory values
        $combinedValue = $memories->pluck('value')->join("\n\n---\n\n");

        // Create the summary memory
        $summaryMemory = Memory::create([
            'agent_id' => $agent->id,
            'key' => $summaryKey,
            'value' => $combinedValue,
            'type' => 'summary',
            'visibility' => 'private',
        ]);

        // Dispatch job to generate the actual summary
        SummarizeMemory::dispatch($summaryMemory);

        // Delete the original memories
        Memory::whereIn('id', $memoryIds)->delete();

        return $summaryMemory;
    }

    // -------------------------------------------------------------------------
    // Access Tracking & Feedback
    // -------------------------------------------------------------------------

    public function recordAccess(Memory $memory): void
    {
        $memory->increment('access_count');
        $memory->update(['last_accessed_at' => now()]);
    }

    public function recordFeedback(Memory $memory, bool $useful): void
    {
        if ($useful) {
            $memory->increment('useful_count');
        }
        // Access is tracked separately — feedback alone doesn't count as access
    }
}
