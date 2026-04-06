<?php

namespace App\Http\Controllers\Api;

use App\Concerns\FormatsMemories;
use App\Http\Controllers\Controller;
use App\Models\AgentActivityLog;
use App\Models\AppStat;
use App\Models\Memory;
use App\Services\AchievementService;
use App\Services\MemorySearchService;
use App\Traits\ApiResponses;
use App\Traits\ResolvesAgent;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;

class MemorySearchController extends Controller
{
    use FormatsMemories, ResolvesAgent, ApiResponses;

    public function __construct(
        private readonly MemorySearchService $searchService,
    ) {}

    // -------------------------------------------------------------------------
    // Semantic search — own memories
    // GET /v1/memories/search?q=...&limit=10
    // -------------------------------------------------------------------------

    public function search(Request $request): JsonResponse
    {
        AppStat::incrementStat('searches_performed');

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $request->validate([
            'q' => ['required', 'string', 'min:1', 'max:500'],
            'limit' => ['nullable', 'integer', 'min:1', 'max:50'],
            'tags' => ['nullable', 'string'],
        ]);

        $tags = $request->has('tags') ? explode(',', $request->input('tags')) : [];
        $type = $request->query('type');
        $category = $request->query('category');
        $detail = $request->query('detail', 'full');

        $results = $this->searchService->searchForAgent(
            $agent,
            $request->string('q'),
            $request->integer('limit', 10),
            $tags,
            $type,
            $category
        );

        app(AchievementService::class)->checkAndAward($agent, 'search');

        try {
            AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'search', 'created_at' => now()]);
        } catch (\Throwable) {
            // Activity logging must never break the main operation
        }

        return $this->success([
            'data' => $results->map(fn ($m) => [
                ...$this->formatMemory($m, $detail),
                'similarity' => round($m->similarity ?? 0, 4),
            ]),
        ]);
    }

    // -------------------------------------------------------------------------
    // Semantic search — public commons
    // GET /v1/commons
    // -------------------------------------------------------------------------

    public function commonsIndex(Request $request): JsonResponse
    {
        $request->validate([
            'limit' => ['nullable', 'integer', 'min:1', 'max:50'],
            'cursor' => ['nullable', 'string'],
            'tags' => ['nullable', 'string'],
        ]);

        $limit = $request->integer('limit', 10);
        $cursor = $request->input('cursor');
        $tags = $request->has('tags') ? explode(',', $request->input('tags')) : [];
        $type = $request->query('type');

        // Only cache the "Front Page" (no cursor, default limit, no tags, no type)
        if ($cursor === null && $limit === 10 && empty($tags) && $type === null) {
            return $this->success(
                Cache::remember('commons_front_page', 5, function () use ($limit) {
                    return $this->getCommonsData($limit, []);
                })
            );
        }

        return $this->success($this->getCommonsData($limit, $tags, $type, $cursor));
    }

    private function getCommonsData(int $limit, array $tags = [], ?string $type = null, ?string $cursor = null): array
    {
        $query = Memory::query()
            ->select('id', 'agent_id', 'workspace_id', 'key', 'value', 'type', 'visibility', 'importance', 'confidence', 'metadata', 'created_at', 'updated_at', 'expires_at')
            ->public()
            ->notExpired()
            ->orderBy('created_at', 'desc')
            ->orderBy('id', 'desc')
            ->with('agent:id,name,description');

        if (! empty($tags)) {
            $query->withTags($tags);
        }

        if ($type) {
            $query->where('type', $type);
        }

        $paginated = $query->cursorPaginate($limit, ['*'], 'cursor', $cursor);

        return [
            'data' => collect($paginated->items())->map(fn (Memory $m) => [
                ...$this->formatMemory($m),
                'agent' => [
                    'id' => $m->agent->id,
                    'name' => $m->agent->name,
                    'description' => $m->agent->description,
                ],
            ]),
            'meta' => [
                'next_cursor' => $paginated->nextCursor()?->encode(),
                'prev_cursor' => $paginated->previousCursor()?->encode(),
                'per_page' => $paginated->perPage(),
                'has_more' => $paginated->hasMorePages(),
            ],
        ];
    }

    // -------------------------------------------------------------------------
    // Semantic search — public commons search
    // GET /v1/commons/search?q=...&limit=10
    // -------------------------------------------------------------------------

    public function commonsSearch(Request $request): JsonResponse
    {
        AppStat::incrementStat('searches_performed');

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $request->validate([
            'q' => ['required', 'string', 'min:1', 'max:500'],
            'limit' => ['nullable', 'integer', 'min:1', 'max:50'],
            'tags' => ['nullable', 'string'],
        ]);

        $tags = $request->has('tags') ? explode(',', $request->input('tags')) : [];
        $type = $request->query('type');
        $category = $request->query('category');
        $detail = $request->query('detail', 'full');

        $results = $this->searchService->searchCommons(
            $agent,
            $request->string('q'),
            $request->integer('limit', 10),
            $tags,
            $type,
            $category
        );

        return $this->success([
            'data' => $results->map(fn ($m) => [
                ...$this->formatMemory($m, $detail),
                'agent' => [
                    'id' => $m->agent->id,
                    'name' => $m->agent->name,
                    'description' => $m->agent->description,
                ],
                'similarity' => round($m->similarity ?? 0, 4),
            ]),
        ]);
    }
}
