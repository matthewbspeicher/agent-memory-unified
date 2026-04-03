<?php

namespace App\Mcp\Tools;

use App\Concerns\FormatsMemories;
use App\Models\Agent;
use App\Models\Memory;
use App\Services\MemoryService;
use Illuminate\Contracts\JsonSchema\JsonSchema;
use Laravel\Mcp\Request;
use Laravel\Mcp\Response;
use Laravel\Mcp\Server\Tool;

class UpdateMemoryTool extends Tool
{
    use FormatsMemories;

    protected string $name = 'update_memory';

    protected string $description = 'Update an existing memory by key';

    public function schema(JsonSchema $schema): array
    {
        return [
            'key' => $schema->string()->description('The memory key to update')->required(),
            'value' => $schema->string()->description('The new memory content'),
            'visibility' => $schema->string()->description('New visibility setting: private, shared, or public')->enum(['private', 'shared', 'public']),
            'type' => $schema->string()->description('New memory type')->enum(Memory::TYPES),
            'metadata' => $schema->object()->description('New metadata object (will replace existing)'),
            'expires_at' => $schema->string()->description('New ISO 8601 expiry timestamp'),
            'ttl' => $schema->string()->description("New shorthand time-to-live (e.g., '24h', '7d', '30m')"),
            'tags' => $schema->array()->description('New array of tags (max 10)')->max(10),
        ];
    }

    public function handle(Request $request, Agent $agent, MemoryService $memories): Response
    {
        $key = $request->get('key');
        $memory = $memories->findByKey($agent, $key);

        if (! $memory) {
            return Response::error("Memory not found: {$key}");
        }

        $data = array_filter([
            'value' => $request->get('value'),
            'visibility' => $request->get('visibility'),
            'type' => $request->get('type'),
            'metadata' => $request->get('metadata'),
            'expires_at' => $request->get('expires_at'),
            'ttl' => $request->get('ttl'),
            'tags' => $request->get('tags'),
        ], fn ($v) => $v !== null);

        if (empty($data)) {
            return Response::error('Must provide at least one field to update.');
        }

        $memory = $memories->update($memory, $data);

        return Response::json($this->formatMemory($memory));
    }
}
