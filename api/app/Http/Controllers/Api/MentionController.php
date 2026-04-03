<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\CollaborationMention;
use App\Models\Workspace;
use App\Models\WorkspaceEvent;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class MentionController extends Controller
{
    /**
     * List mentions for the workspace (sent and received by authenticated agent).
     * GET /v1/workspaces/{id}/mentions
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

        $mentions = CollaborationMention::where('workspace_id', $id)
            ->where(function ($q) use ($agent) {
                $q->where('agent_id', $agent->id)
                    ->orWhere('target_agent_id', $agent->id);
            })
            ->with(['sender:id,name', 'target:id,name'])
            ->orderByDesc('created_at')
            ->limit(50)
            ->get();

        return response()->json([
            'data' => $mentions->map(fn (CollaborationMention $m) => $this->formatMention($m)),
        ]);
    }

    /**
     * List received mentions.
     * GET /v1/workspaces/{id}/mentions/received
     */
    public function received(Request $request, string $id): JsonResponse
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

        $statusFilter = $request->query('status');

        $query = CollaborationMention::where('workspace_id', $id)
            ->where('target_agent_id', $agent->id)
            ->with(['sender:id,name'])
            ->orderByDesc('created_at');

        if ($statusFilter && in_array($statusFilter, ['pending', 'accepted', 'declined', 'completed'], true)) {
            $query->where('status', $statusFilter);
        }

        $mentions = $query->limit(50)->get();

        return response()->json([
            'data' => $mentions->map(fn (CollaborationMention $m) => $this->formatMention($m)),
        ]);
    }

    /**
     * Get a specific mention.
     * GET /v1/workspaces/{id}/mentions/{mentionId}
     */
    public function show(Request $request, string $id, string $mentionId): JsonResponse
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

        $mention = CollaborationMention::where('workspace_id', $id)
            ->where('id', $mentionId)
            ->with(['sender:id,name', 'target:id,name'])
            ->first();

        if (! $mention) {
            return response()->json(['error' => 'Mention not found.'], 404);
        }

        // Only sender or target can view
        if ($mention->agent_id !== $agent->id && $mention->target_agent_id !== $agent->id) {
            return response()->json(['error' => 'Access denied.'], 403);
        }

        return response()->json(['data' => $this->formatMention($mention)]);
    }

    /**
     * Create a @mention.
     * POST /v1/workspaces/{id}/mentions
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
            'target_agent_id' => ['required', 'uuid', 'exists:agents,id',
                function ($attribute, $value, $fail) use ($workspace) {
                    if (! $workspace->agents()->where('agents.id', $value)->exists()) {
                        $fail('Target agent does not belong to this workspace.');
                    }
                },
            ],
            'message' => ['required', 'string', 'min:1', 'max:2000'],
            'memory_id' => ['nullable', 'uuid', 'exists:memories,id'],
            'task_id' => ['nullable', 'uuid', 'exists:workspace_tasks,id'],
        ]);

        // Cannot mention yourself
        if ($validated['target_agent_id'] === $agent->id) {
            return response()->json(['error' => 'Cannot mention yourself.'], 422);
        }

        $mention = CollaborationMention::create([
            'workspace_id' => $id,
            'agent_id' => $agent->id,
            'target_agent_id' => $validated['target_agent_id'],
            'status' => CollaborationMention::STATUS_PENDING,
            'message' => $validated['message'],
            'memory_id' => $validated['memory_id'] ?? null,
            'task_id' => $validated['task_id'] ?? null,
        ]);

        // Dispatch event
        WorkspaceEvent::dispatch(
            $id,
            WorkspaceEvent::TYPE_MENTION_CREATED,
            $agent->id,
            [
                'mention_id' => $mention->id,
                'target_agent_id' => $validated['target_agent_id'],
                'message' => $validated['message'],
            ]
        );

        $mention->load(['sender:id,name', 'target:id,name']);

        return response()->json(['data' => $this->formatMention($mention)], 201);
    }

    /**
     * Respond to a mention.
     * PUT /v1/workspaces/{id}/mentions/{mentionId}/respond
     */
    public function respond(Request $request, string $id, string $mentionId): JsonResponse
    {
        $workspace = Workspace::find($id);
        if (! $workspace) {
            return response()->json(['error' => 'Workspace not found.'], 404);
        }

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $mention = CollaborationMention::where('workspace_id', $id)
            ->where('id', $mentionId)
            ->first();

        if (! $mention) {
            return response()->json(['error' => 'Mention not found.'], 404);
        }

        // Only the target can respond
        if ($mention->target_agent_id !== $agent->id) {
            return response()->json(['error' => 'Only the target agent can respond to a mention.'], 403);
        }

        $validated = $request->validate([
            'response' => ['required', 'string', 'in:accepted,declined,completed'],
        ]);

        $responseText = $request->input('response_text');
        $mention->respond($validated['response'], $responseText);

        // Dispatch event
        WorkspaceEvent::dispatch(
            $id,
            WorkspaceEvent::TYPE_MENTION_RESPONDED,
            $agent->id,
            [
                'mention_id' => $mention->id,
                'sender_agent_id' => $mention->agent_id,
                'response' => $validated['response'],
            ]
        );

        $mention->load(['sender:id,name', 'target:id,name']);

        return response()->json(['data' => $this->formatMention($mention)]);
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

    private function formatMention(CollaborationMention $mention): array
    {
        return [
            'id' => $mention->id,
            'workspace_id' => $mention->workspace_id,
            'agent_id' => $mention->agent_id,
            'target_agent_id' => $mention->target_agent_id,
            'status' => $mention->status,
            'message' => $mention->message,
            'memory_id' => $mention->memory_id,
            'task_id' => $mention->task_id,
            'response' => $mention->response,
            'responded_at' => $mention->responded_at?->toIso8601String(),
            'sender' => $mention->relationLoaded('sender') && $mention->sender ? [
                'id' => $mention->sender->id,
                'name' => $mention->sender->name,
            ] : null,
            'target' => $mention->relationLoaded('target') && $mention->target ? [
                'id' => $mention->target->id,
                'name' => $mention->target->name,
            ] : null,
            'created_at' => $mention->created_at?->toIso8601String(),
            'updated_at' => $mention->updated_at?->toIso8601String(),
        ];
    }
}
