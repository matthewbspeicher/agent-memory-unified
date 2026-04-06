<?php

namespace App\Traits;

use App\Models\Agent;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

trait ResolvesAgent
{
    /**
     * Resolve the active agent for the request.
     * If the actor is an Agent token, use that agent.
     * If the actor is a Workspace token, require 'agent_id' in payload
     * and ensure it belongs to the workspace.
     */
    protected function resolveAgent(Request $request, ?array $validated = null): Agent|JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $workspace = $request->attributes->get('workspace_token');

        if ($agent) {
            return $agent;
        }

        if ($workspace) {
            $agentId = $validated['agent_id'] ?? $request->input('agent_id');
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

        return response()->json(['error' => 'No valid authentication context found.'], 401);
    }
}
