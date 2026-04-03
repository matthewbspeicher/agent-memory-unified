<?php

namespace App\Concerns;

use App\Models\Memory;

trait FormatsMemories
{
    private function formatMemory(Memory $memory, string $detail = 'full'): array
    {
        $metadata = $memory->metadata ?? [];
        $tags = $metadata['tags'] ?? [];
        unset($metadata['tags']);

        $relations = [];
        if ($memory->relationLoaded('relatedTo')) {
            $relations = $memory->relatedTo->map(fn ($rel) => [
                'id' => $rel->id,
                'type' => $rel->pivot->type ?? 'related',
            ])->toArray();
        }

        // When detail=summary and a summary exists, return summary as value
        $value = ($detail === 'summary' && $memory->summary)
            ? $memory->summary
            : $memory->value;

        return [
            'id' => $memory->id,
            'key' => $memory->key,
            'value' => $value,
            'summary' => $memory->summary,
            'type' => $memory->type,
            'category' => $memory->category,
            'visibility' => $memory->visibility,
            'workspace_id' => $memory->workspace_id,
            'importance' => $memory->importance,
            'confidence' => $memory->confidence,
            'access_count' => $memory->access_count ?? 0,
            'useful_count' => $memory->useful_count ?? 0,
            'has_full_content' => ($detail === 'summary' && $memory->summary !== null),
            'metadata' => empty($metadata) ? new \stdClass : $metadata,
            'tags' => array_values($tags),
            'relations' => empty($relations) ? [] : $relations,
            'created_at' => $memory->created_at->toIso8601String(),
            'updated_at' => $memory->updated_at->toIso8601String(),
            'expires_at' => $memory->expires_at?->toIso8601String(),
        ];
    }
}
