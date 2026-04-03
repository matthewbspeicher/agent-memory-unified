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

class ListMemoriesTool extends Tool
{
    use FormatsMemories;

    protected string $name = 'list_memories';

    protected string $description = 'List all memories for the authenticated agent';

    public function schema(JsonSchema $schema): array
    {
        return [
            'page' => $schema->integer()->description('Page number')->default(1),
            'tags' => $schema->string()->description('Comma-separated list of tags to filter by'),
            'type' => $schema->string()->description('Filter results to this memory type')->enum(Memory::TYPES),
        ];
    }

    public function handle(Request $request, Agent $agent, MemoryService $memories): Response
    {
        $tagsString = $request->get('tags', '');
        $tags = $tagsString ? explode(',', $tagsString) : [];
        $type = $request->get('type');

        $paginated = $memories->listForAgent($agent, 20, $tags, $type);

        return Response::json([
            'data' => collect($paginated->items())->map(fn ($m) => $this->formatMemory($m))->values()->all(),
            'meta' => [
                'total' => $paginated->total(),
                'per_page' => $paginated->perPage(),
                'current_page' => $paginated->currentPage(),
                'last_page' => $paginated->lastPage(),
            ],
        ]);
    }
}
