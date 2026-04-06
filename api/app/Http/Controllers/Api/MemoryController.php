<?php

namespace App\Http\Controllers\Api;

use App\Concerns\FormatsMemories;
use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\AgentActivityLog;
use App\Models\AppStat;
use App\Models\Memory;
use App\Models\Workspace;
use App\Models\WorkspaceEvent;
use App\Services\AchievementService;
use App\Http\Requests\StoreMemoryRequest;
use App\Http\Requests\UpdateMemoryRequest;
use App\Services\MemoryService;
use App\Services\SummarizationService;
use App\Traits\ResolvesAgent;
use Closure;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;
use Illuminate\Validation\Rule;

class MemoryController extends Controller
{
    use FormatsMemories;
    use ResolvesAgent;

    public function __construct(
        private readonly MemoryService $memories,
    ) {}

    // -------------------------------------------------------------------------
    // Store a memory
    // POST /v1/memories
    // -------------------------------------------------------------------------

    public function store(StoreMemoryRequest $request): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $validated = $request->validated();

        // Relations need agent-scoped validation (can't go in FormRequest)
        if ($request->has('relations')) {
            $request->validate([
                'relations' => ['nullable', 'array', 'max:50'],
                'relations.*.id' => ['required', 'uuid',
                    function (string $attribute, mixed $value, Closure $fail) use ($agent) {
                        if (! Memory::where('id', $value)->accessibleBy($agent)->exists()) {
                            $fail('The referenced memory does not exist or is not accessible.');
                        }
                    },
                ],
                'relations.*.type' => ['nullable', 'string', 'max:50'],
            ]);
            $validated['relations'] = $request->input('relations');
        }

        // Check workspace membership if storing to a workspace
        if (($validated['visibility'] ?? null) === 'workspace' && ! empty($validated['workspace_id'])) {
            if (! $agent->workspaces()->where('workspaces.id', $validated['workspace_id'])->exists()) {
                return response()->json(['error' => 'Agent does not belong to this workspace.'], 403);
            }
        }

        $memory = $this->memories->store($agent, $validated);

        try {
            AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'store', 'created_at' => now()]);
        } catch (\Throwable) {
            // Activity logging must never break the main operation
        }

        if ($memory->workspace_id) {
            WorkspaceEvent::dispatch($memory->workspace_id, WorkspaceEvent::TYPE_MEMORY_CREATED, $agent->id, [
                'memory_id' => $memory->id,
                'memory_key' => $memory->key,
                'memory_type' => $memory->type,
                'visibility' => $memory->visibility,
            ]);
        }

        return response()->json($this->formatMemory($memory), 201);
    }

    // -------------------------------------------------------------------------
    // Get memory by key
    // GET /v1/memories/{key}
    // -------------------------------------------------------------------------

    public function show(Request $request, string $key): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $memory = $this->memories->findByKey($agent, $key);

        if (! $memory) {
            return response()->json(['error' => 'Memory not found.'], 404);
        }

        // Track access for relevance feedback
        $this->memories->recordAccess($memory);

        $detail = $request->query('detail', 'full');

        return response()->json($this->formatMemory($memory, $detail));
    }

    // -------------------------------------------------------------------------
    // List own memories
    // GET /v1/memories
    // -------------------------------------------------------------------------

    public function index(Request $request): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $tags = $request->has('tags') ? explode(',', $request->input('tags')) : [];
        $type = $request->query('type');
        $category = $request->query('category');
        $detail = $request->query('detail', 'full');
        $paginated = $this->memories->listForAgent($agent, 20, $tags, $type, $category);

        return response()->json([
            'data' => collect($paginated->items())->map(fn ($m) => $this->formatMemory($m, $detail)),
            'meta' => [
                'total' => $paginated->total(),
                'per_page' => $paginated->perPage(),
                'current_page' => $paginated->currentPage(),
                'last_page' => $paginated->lastPage(),
            ],
        ]);
    }

    // -------------------------------------------------------------------------
    // Update a memory
    // PATCH /v1/memories/{key}
    // -------------------------------------------------------------------------

    public function update(UpdateMemoryRequest $request, string $key): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $memory = $this->memories->findByKey($agent, $key);

        if (! $memory) {
            return response()->json(['error' => 'Memory not found.'], 404);
        }

        $validated = $request->validated();

        // Relations need agent-scoped validation (can't go in FormRequest)
        if ($request->has('relations')) {
            $request->validate([
                'relations' => ['sometimes', 'array', 'max:50'],
                'relations.*.id' => ['required', 'uuid',
                    function (string $attribute, mixed $value, Closure $fail) use ($agent) {
                        if (! Memory::where('id', $value)->accessibleBy($agent)->exists()) {
                            $fail('The referenced memory does not exist or is not accessible.');
                        }
                    },
                ],
            'relations.*.type' => ['nullable', 'string', 'max:50'],
            ]);
            $validated['relations'] = $request->input('relations');
        }

        // Check workspace membership if changing to a workspace
        if (($validated['visibility'] ?? null) === 'workspace' && isset($validated['workspace_id'])) {
            if (! $agent->workspaces()->where('workspaces.id', $validated['workspace_id'])->exists()) {
                return response()->json(['error' => 'Agent does not belong to this workspace.'], 403);
            }
        }

        $memory = $this->memories->update($memory, $validated);

        if ($memory->workspace_id) {
            WorkspaceEvent::dispatch($memory->workspace_id, WorkspaceEvent::TYPE_MEMORY_UPDATED, $agent->id, [
                'memory_id' => $memory->id,
                'memory_key' => $memory->key,
                'changes' => array_keys($validated),
            ]);
        }

        return response()->json($this->formatMemory($memory));
    }

    // -------------------------------------------------------------------------
    // Delete a memory
    // DELETE /v1/memories/{key}
    // -------------------------------------------------------------------------

    public function destroy(Request $request, string $key): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $memory = $this->memories->findByKey($agent, $key);

        if (! $memory) {
            return response()->json(['error' => 'Memory not found.'], 404);
        }

        if ($memory->workspace_id) {
            WorkspaceEvent::dispatch($memory->workspace_id, WorkspaceEvent::TYPE_MEMORY_DELETED, $agent->id, [
                'memory_id' => $memory->id,
                'memory_key' => $memory->key,
            ]);
        }

        $this->memories->delete($memory);

        return response()->json(['message' => 'Memory deleted.']);
    }

    // -------------------------------------------------------------------------
    // Compact memories
    // POST /v1/memories/compact
    // -------------------------------------------------------------------------

    public function compact(Request $request): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $validated = $request->validate([
            'memory_ids' => ['required', 'array', 'min:2'],
            'memory_ids.*' => ['uuid', 'exists:memories,id'],
            'summary_key' => ['required', 'string', 'max:255'],
        ]);

        try {
            // T3: Call service method
            $summaryMemory = $this->memories->compact(
                $agent,
                $validated['memory_ids'],
                $validated['summary_key']
            );

            return response()->json([
                'message' => 'Memories compacted successfully.',
                'data' => $summaryMemory,
            ]);

        } catch (\InvalidArgumentException $e) {
            return response()->json(['error' => $e->getMessage()], 422);
        }
    }

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

        $results = $this->memories->searchForAgent(
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

        return response()->json([
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
            return response()->json(
                Cache::remember('commons_front_page', 5, function () use ($limit) {
                    return $this->getCommonsData($limit, []);
                })
            );
        }

        return response()->json($this->getCommonsData($limit, $tags, $type, $cursor));
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
    // Semantic search — public commons
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

        $results = $this->memories->searchCommons(
            $agent,
            $request->string('q'),
            $request->integer('limit', 10),
            $tags,
            $type,
            $category
        );

        return response()->json([
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

    // -------------------------------------------------------------------------
    // Share a memory with another agent
    // POST /v1/memories/{key}/share
    // -------------------------------------------------------------------------

    public function share(Request $request, string $key): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $memory = $this->memories->findByKey($agent, $key);

        if (! $memory) {
            return response()->json(['error' => 'Memory not found.'], 404);
        }

        $validated = $request->validate([
            'agent_id' => ['required', 'uuid', 'exists:agents,id'],
        ]);

        $recipient = Agent::findOrFail($validated['agent_id']);
        $this->memories->shareWith($memory, $recipient);

        app(AchievementService::class)->checkAndAward($agent, 'share');

        try {
            AgentActivityLog::create(['agent_id' => $agent->id, 'action' => 'share', 'created_at' => now()]);
        } catch (\Throwable) {
            // Activity logging must never break the main operation
        }

        return response()->json(['message' => "Memory shared with agent {$recipient->name}."]);
    }

    // -------------------------------------------------------------------------
    // Relevance feedback
    // POST /v1/memories/{key}/feedback
    // -------------------------------------------------------------------------

    public function feedback(Request $request, string $key): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $memory = $this->memories->findByKey($agent, $key);

        if (! $memory) {
            return response()->json(['error' => 'Memory not found.'], 404);
        }

        $validated = $request->validate([
            'useful' => ['required', 'boolean'],
        ]);

        $this->memories->recordFeedback($memory, $validated['useful']);

        app(AchievementService::class)->checkAndAward($memory->agent, 'feedback');

        return response()->json(['message' => 'Feedback recorded.']);
    }
}
