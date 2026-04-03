<?php

namespace App\Services;

use App\Events\MemoryCreated;
use App\Events\MemoryShared;
use App\Jobs\SummarizeMemory;
use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Pagination\LengthAwarePaginator;
use Illuminate\Support\Carbon;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class MemoryService
{
    public function __construct(
        private readonly EmbeddingService $embeddings,
        private readonly SummarizationService $summarizer,
    ) {}

    // -------------------------------------------------------------------------
    // Write
    // -------------------------------------------------------------------------

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
                $syncData = [];
                foreach ($data['relations'] as $relation) {
                    $syncData[$relation['id']] = ['type' => $relation['type'] ?? 'related'];
                }
                $memory->relatedTo()->sync($syncData);
                $memory->load('relatedTo');
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

        try {
            app(AchievementService::class)->checkAndAward($agent, 'store');
        } catch (\Throwable $e) {
            // Achievement check must never break the main operation
        }

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
                $syncData = [];
                foreach ($data['relations'] as $relation) {
                    $syncData[$relation['id']] = ['type' => $relation['type'] ?? 'related'];
                }
                $memory->relatedTo()->sync($syncData);
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
    // Search
    // -------------------------------------------------------------------------

    public function searchForAgent(Agent $agent, string $q, int $limit = 10, array $tags = [], ?string $type = null, ?string $category = null): Collection
    {
        $embedding = $this->embeddings->embed($q);

        $start = microtime(true);

        // 1. Vector Search
        $vectorQuery = Memory::query()
            ->accessibleBy($agent)
            ->notExpired()
            ->with('relatedTo')
            ->semanticSearch($embedding, $limit * 2); // fetch more for RRF

        if (! empty($tags)) {
            $vectorQuery->withTags($tags);
        }
        $vectorQuery->when($type, fn ($query) => $query->where('type', $type));
        $vectorQuery->when($category, fn ($query) => $query->inCategory($category));
        $vectorResults = $vectorQuery->get();

        // 2. Keyword Search
        $keywordQuery = Memory::query()
            ->accessibleBy($agent)
            ->notExpired()
            ->with('relatedTo')
            ->keywordSearch($q, $limit * 2);

        if (! empty($tags)) {
            $keywordQuery->withTags($tags);
        }
        $keywordQuery->when($type, fn ($query) => $query->where('type', $type));
        $keywordQuery->when($category, fn ($query) => $query->inCategory($category));
        $keywordResults = $keywordQuery->get();

        // 3. Reciprocal Rank Fusion
        $results = $this->fuseResults($vectorResults, $keywordResults, $limit);

        $duration = (microtime(true) - $start) * 1000;
        Log::info("Hybrid search (Agent) completed in {$duration}ms", ['agent_id' => $agent->id, 'limit' => $limit, 'tags' => $tags]);

        return collect($results);
    }

    public function searchCommons(Agent $agent, string $q, int $limit = 10, array $tags = [], ?string $type = null, ?string $category = null): Collection
    {
        $embedding = $this->embeddings->embed($q);

        $start = microtime(true);

        // 1. Vector Search
        $vectorQuery = Memory::query()
            ->visibleTo($agent)
            ->notExpired()
            ->with(['agent:id,name,description', 'relatedTo'])
            ->semanticSearch($embedding, $limit * 2);

        if (! empty($tags)) {
            $vectorQuery->withTags($tags);
        }
        $vectorQuery->when($type, fn ($query) => $query->where('type', $type));
        $vectorQuery->when($category, fn ($query) => $query->inCategory($category));
        $vectorResults = $vectorQuery->get();

        // 2. Keyword Search
        $keywordQuery = Memory::query()
            ->visibleTo($agent)
            ->notExpired()
            ->with(['agent:id,name,description', 'relatedTo'])
            ->keywordSearch($q, $limit * 2);

        if (! empty($tags)) {
            $keywordQuery->withTags($tags);
        }
        $keywordQuery->when($type, fn ($query) => $query->where('type', $type));
        $keywordQuery->when($category, fn ($query) => $query->inCategory($category));
        $keywordResults = $keywordQuery->get();

        // 3. Reciprocal Rank Fusion
        $results = $this->fuseResults($vectorResults, $keywordResults, $limit);

        $duration = (microtime(true) - $start) * 1000;
        Log::info("Hybrid search (Commons) completed in {$duration}ms", ['agent_id' => $agent->id, 'limit' => $limit, 'tags' => $tags]);

        return collect($results);
    }

    /**
     * Perform Reciprocal Rank Fusion on two sets of results, augmented with metadata.
     *
     * Base RRF score for an item is: sum(1 / (k + rank))
     * Time Decay: e^(-lambda * days_old) where lambda controls the decay rate.
     * Importance: Scaled 1-10 multiplier.
     * Confidence: 0.0-1.0 multiplier.
     */
    private function fuseResults(Collection $vectorResults, Collection $keywordResults, int $limit = 10, int $k = 60): array
    {
        $scores = [];
        $memories = [];

        $processMemory = function ($memory, $rank) use (&$scores, &$memories, $k) {
            $id = $memory->id;
            if (! isset($scores[$id])) {
                $scores[$id] = 0.0;
                $memories[$id] = $memory;
            }
            $scores[$id] += 1 / ($k + $rank + 1);
        };

        // 1. Calculate base RRF scores
        foreach ($vectorResults as $rank => $memory) {
            $processMemory($memory, $rank);
        }

        foreach ($keywordResults as $rank => $memory) {
            $processMemory($memory, $rank);
        }

        // 2. Apply advanced ranking modifiers
        $now = now();
        $decayLambda = 0.01; // Controls how fast older memories lose value

        foreach ($scores as $id => $baseScore) {
            $memory = $memories[$id];

            // Importance Multiplier (1-10 mapped to 0.5-2.0 or similar)
            // A default importance of 5 yields a 1.0 multiplier (no change)
            // An importance of 10 yields a 1.5 multiplier
            // An importance of 1 yields a 0.6 multiplier
            $importanceMultiplier = 0.5 + ($memory->importance / 10.0);

            // Confidence Multiplier (0.0 to 1.0)
            // A default confidence of 1.0 yields a 1.0 multiplier (no change)
            $confidenceMultiplier = $memory->confidence;

            // Time Decay Multiplier (exponential decay)
            $daysOld = max(0, $memory->created_at->diffInDays($now));
            $timeDecayMultiplier = exp(-$decayLambda * $daysOld);

            // Calculate final augmented score
            $scores[$id] = $baseScore * $importanceMultiplier * $confidenceMultiplier * $timeDecayMultiplier;

            // Relevance multiplier — boost memories marked useful by agents
            if ($memory->access_count > 0) {
                $usefulRatio = $memory->useful_count / $memory->access_count;
                $relevanceMultiplier = 0.8 + (0.4 * $usefulRatio); // range: 0.8 to 1.2
            } else {
                $relevanceMultiplier = 1.0; // neutral for never-accessed
            }
            $scores[$id] *= $relevanceMultiplier;
        }

        // Sort by final score descending
        arsort($scores);

        // Return top results
        $finalResults = [];
        foreach (array_slice(array_keys($scores), 0, $limit) as $id) {
            $finalResults[] = $memories[$id];
        }

        return $finalResults;
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
