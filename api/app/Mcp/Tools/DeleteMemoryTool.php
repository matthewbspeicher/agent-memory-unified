<?php

namespace App\Mcp\Tools;

use App\Models\Agent;
use App\Services\MemoryService;
use Illuminate\Contracts\JsonSchema\JsonSchema;
use Laravel\Mcp\Request;
use Laravel\Mcp\Response;
use Laravel\Mcp\Server\Tool;

class DeleteMemoryTool extends Tool
{
    protected string $name = 'delete_memory';

    protected string $description = 'Delete a memory by key';

    public function schema(JsonSchema $schema): array
    {
        return [
            'key' => $schema->string()->description('The memory key to delete')->required(),
        ];
    }

    public function handle(Request $request, Agent $agent, MemoryService $memories): Response
    {
        $key = $request->get('key');
        $memory = $memories->findByKey($agent, $key);

        if (! $memory) {
            return Response::error("Memory not found: {$key}");
        }

        $memories->delete($memory);

        return Response::text("Memory '{$key}' deleted successfully.");
    }
}
