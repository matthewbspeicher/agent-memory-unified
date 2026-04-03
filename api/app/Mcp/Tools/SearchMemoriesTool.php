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

class SearchMemoriesTool extends Tool
{
    use FormatsMemories;

    protected string $name = 'search_memories';

    protected string $description = 'Semantic search across your own memories';

    public function schema(JsonSchema $schema): array
    {
        return [
            'q' => $schema->string()->description('Natural language search query')->required(),
            'limit' => $schema->integer()->description('Max results to return')->default(10),
            'tags' => $schema->string()->description('Comma-separated list of tags to filter by'),
            'type' => $schema->string()->description('Filter results to this memory type')->enum(Memory::TYPES),
        ];
    }

    public function handle(Request $request, Agent $agent, MemoryService $memories): Response
    {
        $q = $request->get('q');
        $limit = (int) $request->get('limit', 10);
        $tagsString = $request->get('tags', '');
        $tags = $tagsString ? explode(',', $tagsString) : [];
        $type = $request->get('type');

        $results = $memories->searchForAgent($agent, $q, $limit, $tags, $type);

        $data = $results->map(fn ($m) => [
            ...$this->formatMemory($m),
            'similarity' => round($m->similarity ?? 0, 4),
        ]);

        return Response::json(['data' => $data->values()->all()]);
    }
}
