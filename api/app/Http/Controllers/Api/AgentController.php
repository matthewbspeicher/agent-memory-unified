<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\User;
use App\Services\AchievementService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class AgentController extends Controller
{
    /**
     * Register a new agent under a human owner account.
     * Called by humans on behalf of their agents (or by the agent itself on first boot).
     */
    public function register(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'name' => ['required', 'string', 'max:100'],
            'description' => ['nullable', 'string', 'max:500'],
            'owner_token' => ['required', 'string'],
        ]);

        $tokenHash = hash('sha256', $validated['owner_token']);
        $owner = User::where('api_token_hash', $tokenHash)
            ->first();

        if (! $owner) {
            return response()->json(['error' => 'Invalid owner token.'], 401);
        }

        if ($owner->agents()->count() >= $owner->maxAgents()) {
            return response()->json([
                'error' => 'Agent limit reached. Upgrade to Pro for unlimited agents.',
            ], 403);
        }

        $token = Agent::generateToken();

        $agent = Agent::create([
            'owner_id' => $owner->id,
            'name' => $validated['name'],
            'description' => $validated['description'] ?? null,
            'token_hash' => hash('sha256', $token),
        ]);

        try {
            app(AchievementService::class)->checkEarlyAdopter($agent);
        } catch (\Throwable $e) {
            // Achievement check must never break the main operation
        }

        return response()->json([
            'agent_id' => $agent->id,
            'agent_token' => $token,
            'message' => 'Agent registered. Store your agent_token — it will not be shown again.',
        ], 201);
    }

    /**
     * Return public profile of an agent by ID.
     */
    public function show(string $agentId): JsonResponse
    {
        $agent = Agent::findOrFail($agentId);

        return response()->json([
            'id' => $agent->id,
            'name' => $agent->name,
            'description' => $agent->description,
            'memory_count' => $agent->memories()->public()->count(),
            'last_seen_at' => $agent->last_seen_at?->toIso8601String(),
            'member_since' => $agent->created_at->toIso8601String(),
        ]);
    }

    /**
     * Update the authenticated agent's profile.
     */
    public function update(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $validated = $request->validate([
            'description' => 'sometimes|string|max:500',
            'is_listed' => 'sometimes|boolean',
            'broadcasts_signals' => 'nullable|boolean',
        ]);
        $agent->update($validated);
        $agent->refresh();

        return response()->json([
            'id' => $agent->id,
            'name' => $agent->name,
            'description' => $agent->description,
            'is_listed' => $agent->is_listed,
            'memory_count' => $agent->memories()->where('visibility', 'public')->count(),
        ]);
    }

    /**
     * Return the authenticated agent's own profile.
     */
    public function me(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        return response()->json([
            'id' => $agent->id,
            'name' => $agent->name,
            'description' => $agent->description,
            'is_listed' => $agent->is_listed ?? false,
            'memory_count' => $agent->memories()->count(),
            'member_since' => $agent->created_at->toIso8601String(),
            'last_active' => $agent->last_seen_at?->toIso8601String(),
        ]);
    }

    /**
     * Paginated directory of publicly listed agents.
     */
    public function directory(Request $request): JsonResponse
    {
        $sort = $request->input('sort', 'newest');
        $search = $request->input('q');

        $query = Agent::where('is_listed', true)
            ->where('is_active', true)
            ->withCount(['memories as memory_count' => function ($q) {
                $q->where('visibility', 'public');
            }]);

        if ($search) {
            $like = '%'.str_replace(['%', '_'], ['\%', '\_'], $search).'%';
            $query->where(function ($q) use ($like) {
                $q->where('name', 'ilike', $like)
                    ->orWhere('description', 'ilike', $like);
            });
        }

        $query = match ($sort) {
            'memories' => $query->orderByDesc('memory_count'),
            'active' => $query->orderByDesc('last_seen_at'),
            default => $query->orderByDesc('created_at'),
        };

        $agents = $query->paginate(20);

        $agents->getCollection()->transform(function ($agent) {
            return [
                'id' => $agent->id,
                'name' => $agent->name,
                'description' => $agent->description,
                'memory_count' => $agent->memory_count,
                'member_since' => $agent->created_at->toIso8601String(),
                'last_active' => $agent->last_seen_at?->toIso8601String(),
            ];
        });

        return response()->json($agents);
    }
}
