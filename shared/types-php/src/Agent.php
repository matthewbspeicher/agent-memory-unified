<?php

namespace AgentMemory\SharedTypes;

/**
 * Agent profile (manually mirrored from agent.schema.json)
 * TODO: Auto-generate from JSON Schema when tooling improves
 */
readonly class Agent
{
    public function __construct(
        public string $id,
        public string $name,
        public string $owner_id,
        public bool $is_active,
        public array $scopes = [],
        public ?string $created_at = null,
        public ?string $updated_at = null,
    ) {}

    public static function fromArray(array $data): self
    {
        return new self(
            id: $data['id'],
            name: $data['name'],
            owner_id: $data['owner_id'],
            is_active: $data['is_active'],
            scopes: $data['scopes'] ?? [],
            created_at: $data['created_at'] ?? null,
            updated_at: $data['updated_at'] ?? null,
        );
    }

    public function toArray(): array
    {
        return [
            'id' => $this->id,
            'name' => $this->name,
            'owner_id' => $this->owner_id,
            'is_active' => $this->is_active,
            'scopes' => $this->scopes,
            'created_at' => $this->created_at,
            'updated_at' => $this->updated_at,
        ];
    }
}
