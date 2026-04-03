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

class StoreMemoryTool extends Tool
{
    use FormatsMemories;

    protected string $name = 'store_memory';

    protected string $description = 'Store a memory for the authenticated agent';

    public function schema(JsonSchema $schema): array
    {
        return [
            'value' => $schema->string()->description('The memory content to store')->required(),
            'key' => $schema->string()->description('Optional unique key for this memory'),
            'visibility' => $schema->string()->description('Memory visibility: private, shared, or public')->enum(['private', 'shared', 'public'])->default('private'),
            'type' => $schema->string()->description('Memory type: fact, preference, procedure, lesson, error_fix, tool_tip, context, note')->enum(Memory::TYPES)->default('note'),
            'metadata' => $schema->object()->description('Optional metadata object for categorization'),
            'expires_at' => $schema->string()->description('Optional ISO 8601 expiry timestamp'),
            'ttl' => $schema->string()->description("Optional shorthand time-to-live (e.g., '24h', '7d', '30m')"),
            'tags' => $schema->array()->description('Optional array of tags (max 10)')->max(10),
        ];
    }

    public function handle(Request $request, Agent $agent, MemoryService $memories): Response
    {
        $data = array_filter([
            'value' => $request->get('value'),
            'key' => $request->get('key'),
            'visibility' => $request->get('visibility', 'private'),
            'type' => $request->get('type', 'note'),
            'metadata' => $request->get('metadata'),
            'expires_at' => $request->get('expires_at'),
            'ttl' => $request->get('ttl'),
            'tags' => $request->get('tags'),
        ], fn ($v) => $v !== null);

        $memory = $memories->store($agent, $data);

        return Response::json($this->formatMemory($memory));
    }
}
