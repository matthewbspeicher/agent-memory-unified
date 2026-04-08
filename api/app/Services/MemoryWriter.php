<?php

namespace App\Services;

use App\Contracts\EmbeddingServiceInterface;
use App\Contracts\SummarizationServiceInterface;
use App\Events\MemoryCreated;
use App\Events\MemoryStored;
use App\Jobs\SummarizeMemory;
use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use InvalidArgumentException;

class MemoryWriter
{
    public function __construct(
        private readonly EmbeddingServiceInterface $embeddings,
        private readonly SummarizationServiceInterface $summarizer,
    ) {}

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

        $embedding = $this->embeddings->embed($data['value']);
        $summary = $data['summary'] ?? null;

        $memory = DB::transaction(function () use ($agent, $data, $metadata, $embedding, $summary) {
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

        if (! $memory->summary && mb_strlen($memory->value) >= 80) {
            SummarizeMemory::dispatch($memory);
        }

        if ($memory->visibility === 'public') {
            MemoryCreated::dispatch($memory->load('agent'));
        }

        MemoryStored::dispatch($memory);

        return $memory;
    }

    public function update(Memory $memory, array $data): Memory
    {
        if (isset($data['value']) && $data['value'] !== $memory->value) {
            $data['embedding'] = '['.implode(',', $this->embeddings->embed($data['value'])).']';
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

    public function delete(Memory $memory): void
    {
        $memory->delete();
    }

    public function compact(Agent $agent, array $memoryIds, string $summaryKey): Memory
    {
        $memories = Memory::whereIn('id', $memoryIds)
            ->where('agent_id', $agent->id)
            ->get();

        if ($memories->isEmpty()) {
            throw new InvalidArgumentException('No memories found to compact');
        }

        $combinedValue = $memories->pluck('value')->join("\n\n---\n\n");

        $summaryMemory = Memory::create([
            'agent_id' => $agent->id,
            'key' => $summaryKey,
            'value' => $combinedValue,
            'type' => 'summary',
            'visibility' => 'private',
        ]);

        SummarizeMemory::dispatch($summaryMemory);
        Memory::whereIn('id', $memoryIds)->delete();

        return $summaryMemory;
    }

    private function parseTtl(string $ttl): Carbon
    {
        $value = (int) substr($ttl, 0, -1);
        $unit = substr($ttl, -1);

        return match ($unit) {
            'm' => now()->addMinutes($value),
            'h' => now()->addHours($value),
            'd' => now()->addDays($value),
            default => throw new InvalidArgumentException("Invalid TTL format: {$ttl}"),
        };
    }
}
