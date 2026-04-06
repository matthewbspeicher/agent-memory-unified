<?php

namespace AgentMemory\SharedTypes;

/**
 * AI agent with authentication and permissions
 * Auto-generated from JSON Schema - do not edit manually
 */
class Agent
{
    public string $id;
    public string $name;
    public string $owner_id;
    public ?string $token_hash;
    public bool $is_active;
    public ?array $scopes;
    public ?string $description;
    public ?string $creator;
    public ?mixed $last_seen_at;
    public ?string $created_at;
    public ?string $updated_at;

    public function __construct(array $data)
    {
        $this->id = $data['id'] ?? null;
        $this->name = $data['name'] ?? null;
        $this->owner_id = $data['owner_id'] ?? null;
        $this->token_hash = $data['token_hash'] ?? null;
        $this->is_active = $data['is_active'] ?? null;
        $this->scopes = $data['scopes'] ?? null;
        $this->description = $data['description'] ?? null;
        $this->creator = $data['creator'] ?? null;
        $this->last_seen_at = $data['last_seen_at'] ?? null;
        $this->created_at = $data['created_at'] ?? null;
        $this->updated_at = $data['updated_at'] ?? null;
    }

    public static function validationRules(): array
    {
        return [
            'id' => ['required', 'string'],
            'name' => ['required', 'string', 'max:255'],
            'owner_id' => ['required', 'string'],
            'token_hash' => ['string', 'max:64'],
            'is_active' => ['required'],
            'scopes' => [],
            'description' => ['string'],
            'creator' => ['string'],
            'last_seen_at' => [],
            'created_at' => ['string'],
            'updated_at' => ['string'],
        ];
    }
}
