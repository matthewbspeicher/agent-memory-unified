<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\Workspace;
use App\Models\WorkspaceEvent;
use App\Models\WorkspaceTask;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class TaskController extends Controller
{
    /**
     * List tasks in a workspace.
     * GET /v1/workspaces/{id}/tasks
     */
    public function index(Request $request, string $id): JsonResponse
    {
        $workspace = Workspace::find($id);
        if (! $workspace) {
            return response()->json(['error' => 'Workspace not found.'], 404);
        }

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        if (! $this->agentBelongsToWorkspace($agent, $workspace)) {
            return response()->json(['error' => 'Agent does not belong to this workspace.'], 403);
        }

        $request->validate([
            'status' => ['nullable', 'string', 'in:pending,in_progress,completed,failed,cancelled'],
            'assigned_agent_id' => ['nullable', 'uuid'],
            'created_by_agent_id' => ['nullable', 'uuid'],
            'priority' => ['nullable', 'string', 'in:low,medium,high,urgent'],
            'limit' => ['nullable', 'integer', 'min:1', 'max:100'],
        ]);

        $query = WorkspaceTask::where('workspace_id', $id)
            ->with(['creator:id,name', 'assignee:id,name'])
            ->orderByDesc('created_at');

        if ($request->filled('status')) {
            $query->where('status', $request->input('status'));
        }

        if ($request->filled('assigned_agent_id')) {
            $query->where('assigned_agent_id', $request->input('assigned_agent_id'));
        }

        if ($request->filled('created_by_agent_id')) {
            $query->where('created_by_agent_id', $request->input('created_by_agent_id'));
        }

        if ($request->filled('priority')) {
            $query->where('priority', $request->input('priority'));
        }

        $limit = $request->integer('limit', 20);
        $tasks = $query->limit($limit)->get();

        return response()->json([
            'data' => $tasks->map(fn (WorkspaceTask $t) => $this->formatTask($t)),
        ]);
    }

    /**
     * Get a specific task.
     * GET /v1/workspaces/{id}/tasks/{taskId}
     */
    public function show(Request $request, string $id, string $taskId): JsonResponse
    {
        $workspace = Workspace::find($id);
        if (! $workspace) {
            return response()->json(['error' => 'Workspace not found.'], 404);
        }

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        if (! $this->agentBelongsToWorkspace($agent, $workspace)) {
            return response()->json(['error' => 'Agent does not belong to this workspace.'], 403);
        }

        $task = WorkspaceTask::where('workspace_id', $id)
            ->where('id', $taskId)
            ->with(['creator:id,name', 'assignee:id,name'])
            ->first();

        if (! $task) {
            return response()->json(['error' => 'Task not found.'], 404);
        }

        return response()->json(['data' => $this->formatTask($task)]);
    }

    /**
     * Create a task.
     * POST /v1/workspaces/{id}/tasks
     */
    public function store(Request $request, string $id): JsonResponse
    {
        $workspace = Workspace::find($id);
        if (! $workspace) {
            return response()->json(['error' => 'Workspace not found.'], 404);
        }

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        if (! $this->agentBelongsToWorkspace($agent, $workspace)) {
            return response()->json(['error' => 'Agent does not belong to this workspace.'], 403);
        }

        $validated = $request->validate([
            'title' => ['required', 'string', 'min:1', 'max:500'],
            'description' => ['nullable', 'string', 'max:5000'],
            'priority' => ['nullable', 'string', 'in:low,medium,high,urgent'],
            'assigned_agent_id' => ['nullable', 'uuid', 'exists:agents,id',
                function ($attribute, $value, $fail) use ($workspace) {
                    if ($value && ! $workspace->agents()->where('agents.id', $value)->exists()) {
                        $fail('Assigned agent does not belong to this workspace.');
                    }
                },
            ],
            'due_at' => ['nullable', 'date', 'after:now'],
        ]);

        $task = WorkspaceTask::create([
            'workspace_id' => $id,
            'created_by_agent_id' => $agent->id,
            'title' => $validated['title'],
            'description' => $validated['description'] ?? null,
            'status' => WorkspaceTask::STATUS_PENDING,
            'priority' => $validated['priority'] ?? WorkspaceTask::PRIORITY_MEDIUM,
            'assigned_agent_id' => $validated['assigned_agent_id'] ?? null,
            'due_at' => $validated['due_at'] ?? null,
        ]);

        // Dispatch event
        WorkspaceEvent::dispatch(
            $id,
            WorkspaceEvent::TYPE_TASK_CREATED,
            $agent->id,
            [
                'task_id' => $task->id,
                'title' => $task->title,
                'assigned_agent_id' => $task->assigned_agent_id,
            ]
        );

        if ($task->assigned_agent_id) {
            WorkspaceEvent::dispatch(
                $id,
                WorkspaceEvent::TYPE_TASK_ASSIGNED,
                $agent->id,
                [
                    'task_id' => $task->id,
                    'assigned_agent_id' => $task->assigned_agent_id,
                ]
            );
        }

        $task->load(['creator:id,name', 'assignee:id,name']);

        return response()->json(['data' => $this->formatTask($task)], 201);
    }

    /**
     * Update a task.
     * PUT /v1/workspaces/{id}/tasks/{taskId}
     */
    public function update(Request $request, string $id, string $taskId): JsonResponse
    {
        $task = WorkspaceTask::where('workspace_id', $id)
            ->where('id', $taskId)
            ->first();

        if (! $task) {
            return response()->json(['error' => 'Task not found.'], 404);
        }

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $workspace = Workspace::find($id);
        if (! $this->agentBelongsToWorkspace($agent, $workspace)) {
            return response()->json(['error' => 'Agent does not belong to this workspace.'], 403);
        }

        $validated = $request->validate([
            'title' => ['sometimes', 'string', 'min:1', 'max:500'],
            'description' => ['sometimes', 'nullable', 'string', 'max:5000'],
            'priority' => ['sometimes', 'string', 'in:low,medium,high,urgent'],
            'due_at' => ['sometimes', 'nullable', 'date'],
        ]);

        $task->update($validated);

        // Dispatch event
        WorkspaceEvent::dispatch(
            $id,
            WorkspaceEvent::TYPE_TASK_UPDATED,
            $agent->id,
            ['task_id' => $task->id, 'changes' => $validated]
        );

        $task->load(['creator:id,name', 'assignee:id,name']);

        return response()->json(['data' => $this->formatTask($task)]);
    }

    /**
     * Assign a task to an agent.
     * PUT /v1/workspaces/{id}/tasks/{taskId}/assign
     */
    public function assign(Request $request, string $id, string $taskId): JsonResponse
    {
        $task = WorkspaceTask::where('workspace_id', $id)
            ->where('id', $taskId)
            ->first();

        if (! $task) {
            return response()->json(['error' => 'Task not found.'], 404);
        }

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $workspace = Workspace::find($id);
        if (! $this->agentBelongsToWorkspace($agent, $workspace)) {
            return response()->json(['error' => 'Agent does not belong to this workspace.'], 403);
        }

        $validated = $request->validate([
            'agent_id' => ['required', 'uuid', 'exists:agents,id',
                function ($attribute, $value, $fail) use ($workspace) {
                    if (! $workspace->agents()->where('agents.id', $value)->exists()) {
                        $fail('Agent does not belong to this workspace.');
                    }
                },
            ],
        ]);

        $targetAgent = Agent::find($validated['agent_id']);
        $task->assignTo($targetAgent);

        // Dispatch event
        WorkspaceEvent::dispatch(
            $id,
            WorkspaceEvent::TYPE_TASK_ASSIGNED,
            $agent->id,
            [
                'task_id' => $task->id,
                'assigned_agent_id' => $validated['agent_id'],
            ]
        );

        $task->load(['creator:id,name', 'assignee:id,name']);

        return response()->json(['data' => $this->formatTask($task)]);
    }

    /**
     * Update task status.
     * PUT /v1/workspaces/{id}/tasks/{taskId}/status
     */
    public function updateStatus(Request $request, string $id, string $taskId): JsonResponse
    {
        $task = WorkspaceTask::where('workspace_id', $id)
            ->where('id', $taskId)
            ->first();

        if (! $task) {
            return response()->json(['error' => 'Task not found.'], 404);
        }

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $workspace = Workspace::find($id);
        if (! $this->agentBelongsToWorkspace($agent, $workspace)) {
            return response()->json(['error' => 'Agent does not belong to this workspace.'], 403);
        }

        $validated = $request->validate([
            'status' => ['required', 'string', 'in:pending,in_progress,completed,failed,cancelled'],
        ]);

        $newStatus = $validated['status'];
        $updates = ['status' => $newStatus];

        if ($newStatus === 'completed') {
            $updates['completed_at'] = now();
        }

        $task->update($updates);

        $eventType = match ($newStatus) {
            'completed' => WorkspaceEvent::TYPE_TASK_COMPLETED,
            default => WorkspaceEvent::TYPE_TASK_UPDATED,
        };

        WorkspaceEvent::dispatch(
            $id,
            $eventType,
            $agent->id,
            ['task_id' => $task->id, 'new_status' => $newStatus]
        );

        $task->load(['creator:id,name', 'assignee:id,name']);

        return response()->json(['data' => $this->formatTask($task)]);
    }

    /**
     * Delete a task.
     * DELETE /v1/workspaces/{id}/tasks/{taskId}
     */
    public function destroy(Request $request, string $id, string $taskId): JsonResponse
    {
        $task = WorkspaceTask::where('workspace_id', $id)
            ->where('id', $taskId)
            ->first();

        if (! $task) {
            return response()->json(['error' => 'Task not found.'], 404);
        }

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        // Only creator can delete
        if ($task->created_by_agent_id !== $agent->id) {
            return response()->json(['error' => 'Only the task creator can delete a task.'], 403);
        }

        $task->delete();

        return response()->json(['message' => 'Task deleted.']);
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private function resolveAgent(Request $request): Agent|JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $workspace = $request->attributes->get('workspace_token');

        if ($agent) {
            return $agent;
        }

        if ($workspace) {
            $agentId = $request->input('agent_id');
            if (! $agentId) {
                return response()->json(['error' => 'agent_id is required when authenticating via Workspace token.'], 422);
            }

            $agent = Agent::find($agentId);
            if (! $agent) {
                return response()->json(['error' => 'Agent not found.'], 404);
            }

            if (! $workspace->agents()->where('agents.id', $agentId)->exists()) {
                return response()->json(['error' => 'Agent does not belong to this Workspace.'], 403);
            }

            return $agent;
        }

        return response()->json(['error' => 'Unauthorized.'], 401);
    }

    private function agentBelongsToWorkspace(Agent $agent, Workspace $workspace): bool
    {
        return $agent->workspaces()->where('workspaces.id', $workspace->id)->exists();
    }

    private function formatTask(WorkspaceTask $task): array
    {
        return [
            'id' => $task->id,
            'workspace_id' => $task->workspace_id,
            'created_by_agent_id' => $task->created_by_agent_id,
            'assigned_agent_id' => $task->assigned_agent_id,
            'title' => $task->title,
            'description' => $task->description,
            'status' => $task->status,
            'priority' => $task->priority,
            'due_at' => $task->due_at?->toIso8601String(),
            'completed_at' => $task->completed_at?->toIso8601String(),
            'is_overdue' => $task->isOverdue(),
            'creator' => $task->relationLoaded('creator') && $task->creator ? [
                'id' => $task->creator->id,
                'name' => $task->creator->name,
            ] : null,
            'assignee' => $task->relationLoaded('assignee') && $task->assignee ? [
                'id' => $task->assignee->id,
                'name' => $task->assignee->name,
            ] : null,
            'created_at' => $task->created_at?->toIso8601String(),
            'updated_at' => $task->updated_at?->toIso8601String(),
        ];
    }
}
