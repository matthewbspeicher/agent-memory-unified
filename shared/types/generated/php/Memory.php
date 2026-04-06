<?php

namespace AgentMemory\SharedTypes;

/**
 * Knowledge record stored by an agent
 * Auto-generated from JSON Schema - do not edit manually
 */
class Memory
{
    public string $id;
    public string $agent_id;
    public string $value;
    public ?string $type;
    public ?string $summary;
    public ?array $tags;
    public string $visibility;
    public ?int $importance;
    public ?array $embedding;
    public ?string $created_at;

    public function __construct(array $data)
    {
        $this->id = $data['id'] ?? null;
        $this->agent_id = $data['agent_id'] ?? null;
        $this->value = $data['value'] ?? null;
        $this->type = $data['type'] ?? null;
        $this->summary = $data['summary'] ?? null;
        $this->tags = $data['tags'] ?? null;
        $this->visibility = $data['visibility'] ?? null;
        $this->importance = $data['importance'] ?? null;
        $this->embedding = $data['embedding'] ?? null;
        $this->created_at = $data['created_at'] ?? null;
    }

    public static function validationRules(): array
    {
        return [
            'id' => ['required', 'string'],
            'agent_id' => ['required', 'string'],
            'value' => ['required', 'string', 'max:50000'],
            'type' => ['string', 'in:note,lesson,preference,fact,procedure'],
            'summary' => ['string', 'max:500'],
            'tags' => [],
            'visibility' => ['required', 'string', 'in:private,public'],
            'importance' => ['integer'],
            'embedding' => [],
            'created_at' => ['string'],
        ];
    }
}
