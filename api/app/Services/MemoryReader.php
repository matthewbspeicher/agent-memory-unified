<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Pagination\LengthAwarePaginator;

class MemoryReader
{
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
    }
}
