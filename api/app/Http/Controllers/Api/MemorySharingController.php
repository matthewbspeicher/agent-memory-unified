<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\AgentActivityLog;
use App\Models\Memory;
use App\Services\AchievementService;
use App\Services\MemoryService;
use App\Traits\ApiResponses;
use App\Traits\ResolvesAgent;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class MemorySharingController extends Controller
{
    use ResolvesAgent, ApiResponses;

    public function __construct(
        private readonly MemoryService $memories,
    ) {}

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
            return $this->notFound('Memory');
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

        return $this->success(['message' => "Memory shared with agent {$recipient->name}."]);
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
            return $this->notFound('Memory');
        }

        $validated = $request->validate([
            'useful' => ['required', 'boolean'],
        ]);

        $this->memories->recordFeedback($memory, $validated['useful']);

        app(AchievementService::class)->checkAndAward($memory->agent, 'feedback');

        return $this->success(['message' => 'Feedback recorded.']);
    }
}
