<?php

namespace AgentMemory\SharedTypes;

/**
 * Base event structure for Redis Streams
 * Auto-generated from JSON Schema - do not edit manually
 */
class Event
{
    public string $id;
    public string $type;
    public string $version;
    public string $timestamp;
    public string $source;
    public array $payload;
    public ?array $metadata;

    public function __construct(array $data)
    {
        $this->id = $data['id'] ?? null;
        $this->type = $data['type'] ?? null;
        $this->version = $data['version'] ?? null;
        $this->timestamp = $data['timestamp'] ?? null;
        $this->source = $data['source'] ?? null;
        $this->payload = $data['payload'] ?? null;
        $this->metadata = $data['metadata'] ?? null;
    }

    public static function validationRules(): array
    {
        return [
            'id' => ['required', 'string'],
            'type' => ['required', 'string'],
            'version' => ['required', 'string'],
            'timestamp' => ['required', 'string'],
            'source' => ['required', 'string', 'in:memory-api,trading-engine'],
            'payload' => ['required'],
            'metadata' => [],
        ];
    }
}
