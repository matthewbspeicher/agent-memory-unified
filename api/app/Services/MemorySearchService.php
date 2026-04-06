<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Log;

class MemorySearchService
{
    public function __construct(
        private readonly EmbeddingService $embeddings,
    ) {}

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
}
