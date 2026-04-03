<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Workspace;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class WorkspaceController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $workspaces = $agent->workspaces()->get();

        return response()->json(['data' => $workspaces]);
    }

    public function store(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $validated = $request->validate([
            'name' => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string', 'max:1000'],
            'is_guild' => ['boolean'],
        ]);

        $owner = $agent->owner;

        if (! $owner->canCreateWorkspace()) {
            return response()->json([
                'error' => 'Private workspaces require a Pro subscription.',
            ], 403);
        }

        $workspace = Workspace::create([
            'name' => $validated['name'],
            'description' => $validated['description'] ?? null,
            'owner_id' => $agent->owner_id, // Link to the same owner as the agent
            'is_guild' => $validated['is_guild'] ?? false,
        ]);

        // Automatically add the creator agent to the workspace
        $agent->workspaces()->attach($workspace->id);

        return response()->json($workspace, 201);
    }

    public function join(Request $request, string $workspaceId): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $workspace = Workspace::findOrFail($workspaceId);

        // Security check: Only allow agents with the same owner to join without an invite.
        // In a real system, you might have invite codes or a more complex ACL.
        if ($workspace->owner_id !== $agent->owner_id) {
            return response()->json(['error' => 'You do not have permission to join this workspace.'], 403);
        }

        $agent->workspaces()->syncWithoutDetaching([$workspace->id]);

        return response()->json(['message' => "Joined workspace {$workspace->name}"]);
    }
}
