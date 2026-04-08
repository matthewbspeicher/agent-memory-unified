<?php

namespace App\Http\Controllers\Api;

use App\Concerns\FormatsMemories;
use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\AgentActivityLog;
use App\Models\Memory;
use App\Models\Workspace;
use App\Models\WorkspaceEvent;
use App\Http\Requests\StoreMemoryRequest;
use App\Http\Requests\UpdateMemoryRequest;
use App\Services\MemoryService;
use App\Traits\ApiResponses;
use App\Traits\ResolvesAgent;
use Closure;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class MemoryController extends Controller
{
    use FormatsMemories, ResolvesAgent, ApiResponses;

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
                return $this->error('Agent does not belong to this workspace.', 403);
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

        return $this->success($this->formatMemory($memory), 201);
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
            return $this->notFound('Memory');
        }

        // Track access for relevance feedback
        $this->memories->recordAccess($memory);

        $detail = $request->query('detail', 'full');

        return $this->success($this->formatMemory($memory, $detail));
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

        return $this->success([
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
            return $this->notFound('Memory');
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
                return $this->error('Agent does not belong to this workspace.', 403);
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

        return $this->success($this->formatMemory($memory));
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
            return $this->notFound('Memory');
        }

        $this->authorize('delete', $memory);

        if ($memory->workspace_id) {
            WorkspaceEvent::dispatch($memory->workspace_id, WorkspaceEvent::TYPE_MEMORY_DELETED, $agent->id, [
                'memory_id' => $memory->id,
                'memory_key' => $memory->key,
            ]);
        }

        $this->memories->delete($memory);

        return $this->success(['message' => 'Memory deleted.']);
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
            $summaryMemory = $this->memories->compact(
                $agent,
                $validated['memory_ids'],
                $validated['summary_key']
            );

            return $this->success([
                'message' => 'Memories compacted successfully.',
                'data' => $summaryMemory,
            ]);

        } catch (\InvalidArgumentException $e) {
            return $this->error($e->getMessage());
        }
    }
}
