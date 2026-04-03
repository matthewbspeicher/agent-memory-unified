<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\Workspace;
use App\Models\WorkspaceEvent;
use App\Models\WorkspaceSubscription;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class SubscriptionController extends Controller
{
    /**
     * List subscriptions for the authenticated agent in a workspace.
     * GET /v1/workspaces/{id}/subscriptions
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

        $subscriptions = WorkspaceSubscription::where('workspace_id', $id)
            ->where('agent_id', $agent->id)
            ->orderByDesc('created_at')
            ->get();

        return response()->json([
            'data' => $subscriptions->map(fn (WorkspaceSubscription $s) => $this->formatSubscription($s)),
        ]);
    }

    /**
     * Create a new subscription.
     * POST /v1/workspaces/{id}/subscriptions
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
            'event_types' => ['required', 'array', 'min:1', 'max:20'],
            'event_types.*' => ['string', 'max:100'],
            'callback_url' => ['nullable', 'url', 'max:500'],
        ]);

        $subscription = WorkspaceSubscription::create([
            'workspace_id' => $id,
            'agent_id' => $agent->id,
            'event_types' => $validated['event_types'],
            'callback_url' => $validated['callback_url'] ?? null,
        ]);

        return response()->json(['data' => $this->formatSubscription($subscription)], 201);
    }

    /**
     * Update a subscription.
     * PUT /v1/workspaces/{id}/subscriptions/{subscriptionId}
     */
    public function update(Request $request, string $id, string $subscriptionId): JsonResponse
    {
        $subscription = WorkspaceSubscription::where('workspace_id', $id)
            ->where('id', $subscriptionId)
            ->first();

        if (! $subscription) {
            return response()->json(['error' => 'Subscription not found.'], 404);
        }

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        if ($subscription->agent_id !== $agent->id) {
            return response()->json(['error' => 'You can only update your own subscriptions.'], 403);
        }

        $validated = $request->validate([
            'event_types' => ['sometimes', 'array', 'min:1', 'max:20'],
            'event_types.*' => ['string', 'max:100'],
            'callback_url' => ['sometimes', 'nullable', 'url', 'max:500'],
        ]);

        $subscription->update($validated);

        return response()->json(['data' => $this->formatSubscription($subscription)]);
    }

    /**
     * Delete a subscription.
     * DELETE /v1/workspaces/{id}/subscriptions/{subscriptionId}
     */
    public function destroy(Request $request, string $id, string $subscriptionId): JsonResponse
    {
        $subscription = WorkspaceSubscription::where('workspace_id', $id)
            ->where('id', $subscriptionId)
            ->first();

        if (! $subscription) {
            return response()->json(['error' => 'Subscription not found.'], 404);
        }

        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        if ($subscription->agent_id !== $agent->id) {
            return response()->json(['error' => 'You can only delete your own subscriptions.'], 403);
        }

        $subscription->delete();

        return response()->json(['message' => 'Subscription deleted.']);
    }

    /**
     * Poll for events.
     * GET /v1/workspaces/{id}/events
     */
    public function events(Request $request, string $id): JsonResponse
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
            'limit' => ['nullable', 'integer', 'min:1', 'max:100'],
            'cursor' => ['nullable', 'string'],
            'event_type' => ['nullable', 'string'],
        ]);

        $limit = $request->integer('limit', 20);
        $cursor = $request->input('cursor');
        $eventType = $request->input('event_type');

        $query = WorkspaceEvent::where('workspace_id', $id)
            ->orderBy('created_at', 'asc')
            ->orderBy('id', 'asc');

        if ($eventType) {
            $query->where('event_type', $eventType);
        }

        if ($cursor) {
            $cursorEvent = WorkspaceEvent::find($cursor);
            if ($cursorEvent) {
                $query->where(function ($q) use ($cursorEvent) {
                    $q->where('created_at', '>', $cursorEvent->created_at)
                        ->orWhere(function ($q2) use ($cursorEvent) {
                            $q2->where('created_at', '=', $cursorEvent->created_at)
                                ->where('id', '>', $cursorEvent->id);
                        });
                });
            }
        }

        $events = $query->limit($limit + 1)->get();
        $hasMore = $events->count() > $limit;

        if ($hasMore) {
            $events->pop();
        }

        $nextCursor = $hasMore && $events->isNotEmpty() ? $events->last()->id : null;

        return response()->json([
            'data' => $events->map(fn (WorkspaceEvent $e) => $this->formatEvent($e)),
            'meta' => [
                'next_cursor' => $nextCursor,
                'has_more' => $hasMore,
                'per_page' => $limit,
            ],
        ]);
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

    private function formatSubscription(WorkspaceSubscription $subscription): array
    {
        return [
            'id' => $subscription->id,
            'workspace_id' => $subscription->workspace_id,
            'agent_id' => $subscription->agent_id,
            'event_types' => $subscription->event_types,
            'callback_url' => $subscription->callback_url,
            'last_polled_at' => $subscription->last_polled_at?->toIso8601String(),
            'created_at' => $subscription->created_at?->toIso8601String(),
            'updated_at' => $subscription->updated_at?->toIso8601String(),
        ];
    }

    private function formatEvent(WorkspaceEvent $event): array
    {
        return [
            'id' => $event->id,
            'event_type' => $event->event_type,
            'actor_agent_id' => $event->actor_agent_id,
            'payload' => $event->payload,
            'created_at' => $event->created_at?->toIso8601String(),
        ];
    }
}
