<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\AgentPresence;
use App\Models\Workspace;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

class PresenceController extends Controller
{
    /**
     * List all agent presences in a workspace.
     * GET /v1/workspaces/{workspaceId}/presence
     */
    public function index(Request $request, string $workspaceId): JsonResponse
    {
        $workspace = Workspace::find($workspaceId);
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
        $includeOffline = $request->boolean('include_offline', false);

        $query = AgentPresence::where('workspace_id', $workspaceId)
            ->with('agent:id,name,description');

        if ($statusFilter && in_array($statusFilter, [AgentPresence::STATUS_ONLINE, AgentPresence::STATUS_AWAY, AgentPresence::STATUS_BUSY], true)) {
            $query->where('status', $statusFilter);
        }

        if (! $includeOffline) {
            $query->active();
        }

        $presences = $query->orderByDesc('last_seen_at')->get();

        return response()->json([
            'data' => $presences->map(fn (AgentPresence $presence) => $this->formatPresence($presence)),
        ]);
    }

    /**
     * Get a specific agent's presence in a workspace.
     * GET /v1/workspaces/{workspaceId}/presence/{agentId}
     */
    public function show(Request $request, string $workspaceId, string $agentId): JsonResponse
    {
        $workspace = Workspace::find($workspaceId);
        if (! $workspace) {
            return response()->json(['error' => 'Workspace not found.'], 404);
        }

        $authAgent = $this->resolveAgent($request);
        if ($authAgent instanceof JsonResponse) {
            return $authAgent;
        }

        if (! $this->agentBelongsToWorkspace($authAgent, $workspace)) {
            return response()->json(['error' => 'Agent does not belong to this workspace.'], 403);
        }

        $presence = AgentPresence::where('workspace_id', $workspaceId)
            ->where('agent_id', $agentId)
            ->with('agent:id,name,description')
            ->first();

        if (! $presence) {
            return response()->json(['error' => 'Presence not found.'], 404);
        }

        return response()->json(['data' => $this->formatPresence($presence)]);
    }

    /**
     * Update agent's presence (heartbeat).
     * POST /v1/workspaces/{workspaceId}/presence/heartbeat
     */
    public function heartbeat(Request $request, string $workspaceId): JsonResponse
    {
        $workspace = Workspace::find($workspaceId);
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
            'status' => ['sometimes', Rule::in([
                AgentPresence::STATUS_ONLINE,
                AgentPresence::STATUS_AWAY,
                AgentPresence::STATUS_BUSY,
            ])],
            'metadata' => ['sometimes', 'array'],
        ]);

        $presence = AgentPresence::updateOrCreate(
            [
                'workspace_id' => $workspaceId,
                'agent_id' => $agent->id,
            ],
            [
                'status' => $validated['status'] ?? AgentPresence::STATUS_ONLINE,
                'last_seen_at' => now(),
            ]
        );

        if (isset($validated['metadata']) && is_array($validated['metadata'])) {
            $presence->metadata = array_merge($presence->metadata ?? [], $validated['metadata']);
            $presence->save();
        }

        $presence->load('agent:id,name,description');

        return response()->json(['data' => $this->formatPresence($presence)]);
    }

    /**
     * Set agent as offline.
     * POST /v1/workspaces/{workspaceId}/presence/offline
     */
    public function offline(Request $request, string $workspaceId): JsonResponse
    {
        $workspace = Workspace::find($workspaceId);
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

        $presence = AgentPresence::where('workspace_id', $workspaceId)
            ->where('agent_id', $agent->id)
            ->first();

        if (! $presence) {
            return response()->json(['error' => 'Presence not found.'], 404);
        }

        $presence->update(['status' => AgentPresence::STATUS_OFFLINE]);

        return response()->json(['message' => 'Presence set to offline.']);
    }

    /**
     * Resolve the active agent for the request.
     */
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

    /**
     * Check if agent belongs to workspace.
     */
    private function agentBelongsToWorkspace(Agent $agent, Workspace $workspace): bool
    {
        return $agent->workspaces()->where('workspaces.id', $workspace->id)->exists();
    }

    /**
     * Format presence for API response.
     */
    private function formatPresence(AgentPresence $presence): array
    {
        return [
            'id' => $presence->id,
            'workspace_id' => $presence->workspace_id,
            'agent_id' => $presence->agent_id,
            'status' => $presence->status,
            'is_stale' => $presence->isStale(),
            'last_seen_at' => $presence->last_seen_at?->toIso8601String(),
            'metadata' => $presence->metadata,
            'agent' => $presence->relationLoaded('agent') && $presence->agent ? [
                'id' => $presence->agent->id,
                'name' => $presence->agent->name,
                'description' => $presence->agent->description,
            ] : null,
            'created_at' => $presence->created_at?->toIso8601String(),
            'updated_at' => $presence->updated_at?->toIso8601String(),
        ];
    }
}
