<?php

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class MemoryResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        $metadata = $this->metadata ?? [];
        $tags = $metadata['tags'] ?? [];
        unset($metadata['tags']);

        $relations = [];
        if ($this->relationLoaded('relatedTo')) {
            $relations = $this->relatedTo->map(fn ($rel) => [
                'id' => $rel->id,
                'type' => $rel->pivot->type ?? 'related',
            ])->toArray();
        }

        return [
            'id' => $this->id,
            'key' => $this->key,
            'value' => $this->value,
            'type' => $this->type,
            'visibility' => $this->visibility,
            'workspace_id' => $this->workspace_id,
            'importance' => $this->importance,
            'confidence' => $this->confidence,
            'metadata' => empty($metadata) ? new \stdClass : $metadata,
            'tags' => array_values($tags),
            'relations' => empty($relations) ? [] : $relations,
            'created_at' => $this->created_at->toIso8601String(),
            'updated_at' => $this->updated_at->toIso8601String(),
            'expires_at' => $this->expires_at?->toIso8601String(),
            $this->mergeWhen($this->relationLoaded('agent') && $this->agent, [
                'agent' => [
                    'id' => $this->agent?->id,
                    'name' => $this->agent?->name,
                    'description' => $this->agent?->description,
                ],
            ]),
            $this->mergeWhen(isset($this->similarity), [
                'similarity' => round($this->similarity ?? 0, 4),
            ]),
        ];
    }
}
