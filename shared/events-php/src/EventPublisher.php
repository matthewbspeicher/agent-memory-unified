<?php

namespace AgentMemory\SharedEvents;

use Illuminate\Support\Str;

class EventPublisher
{
    public function __construct(
        private \Redis|\Predis\Client $redis,
        private string $stream = 'events'
    ) {}

    /**
     * Publish event to Redis Stream.
     *
     * @param string $type Event type (e.g., 'trade.opened', 'memory.created')
     * @param array $payload Event-specific data
     * @param array $metadata Optional metadata (request_id, etc.)
     */
    public function publish(string $type, array $payload, array $metadata = []): void
    {
        $event = [
            'id' => Str::uuid()->toString(),
            'type' => $type,
            'version' => '1.0',
            'timestamp' => now()->toIso8601String(),
            'source' => 'api',
            'payload' => $payload,
            'metadata' => $metadata,
        ];

        // XADD with MAXLEN ~ 10000 to cap stream size
        // '*' = auto-generate message ID
        // ~ = approximate trimming (more efficient than exact)
        $this->redis->xAdd(
            $this->stream,
            '*',
            ['data' => json_encode($event)],
            10000,  // MAXLEN
            true    // approximate (~)
        );
    }
}
