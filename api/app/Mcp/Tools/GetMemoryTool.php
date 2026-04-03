<?php

namespace App\Mcp\Tools;

use App\Concerns\FormatsMemories;
use App\Models\Agent;
use App\Services\MemoryService;
use Illuminate\Contracts\JsonSchema\JsonSchema;
use Laravel\Mcp\Request;
use Laravel\Mcp\Response;
use Laravel\Mcp\Server\Tool;

class GetMemoryTool extends Tool
{
    use FormatsMemories;

    protected string $name = 'get_memory';

    protected string $description = 'Retrieve a specific memory by key';

    public function schema(JsonSchema $schema): array
    {
        return [
            'key' => $schema->string()->description('The memory key to retrieve')->required(),
        ];
    }

    public function handle(Request $request, Agent $agent, MemoryService $memories): Response
    {
        $key = $request->get('key');
        $memory = $memories->findByKey($agent, $key);

        if (! $memory) {
            return Response::error("Memory not found: {$key}");
        }

        return Response::json($this->formatMemory($memory));
    }
}
