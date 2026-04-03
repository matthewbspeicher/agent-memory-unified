<?php

namespace App\Http\Controllers\Api;

use App\Concerns\FormatsMemories;
use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Services\AchievementService;
use App\Services\MemoryService;
use App\Services\SummarizationService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class SessionController extends Controller
{
    use FormatsMemories;

    public function __construct(
        private readonly MemoryService $memories,
        private readonly SummarizationService $summarizer,
    ) {}

    /**
     * Extract durable memories from a conversation transcript.
     * POST /v1/sessions/extract
     */
    public function extract(Request $request): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $validated = $request->validate([
            'agent_id' => ['sometimes', 'uuid'],
            'transcript' => ['required', 'string', 'min:20', 'max:50000'],
            'category' => ['nullable', 'string', 'max:100'],
            'visibility' => ['nullable', 'in:private,shared,public,workspace'],
        ]);

        try {
            $extracted = $this->summarizer->extractMemories(
                $validated['transcript'],
                $agent
            );
        } catch (\Exception $e) {
            Log::error('Session extraction failed', ['exception' => $e]);

            return response()->json(['error' => 'Failed to extract memories from transcript. Please try again later.'], 500);
        }

        if (empty($extracted)) {
            return response()->json([
                'data' => [],
                'meta' => ['extracted_count' => 0],
            ]);
        }

        $created = [];
        foreach ($extracted as $item) {
            try {
                $memoryData = [
                    'key' => $item['key'],
                    'value' => $item['value'],
                    'type' => $item['type'],
                    'importance' => $item['importance'],
                    'category' => $validated['category'] ?? 'session-extraction',
                    'visibility' => $validated['visibility'] ?? 'private',
                ];

                $memory = $this->memories->store($agent, $memoryData);
                $created[] = $this->formatMemory($memory);
            } catch (\Exception $e) {
                // Skip individual failures (e.g. duplicate keys) but continue
                Log::warning('Skipped extracted memory', [
                    'key' => $item['key'] ?? 'unknown',
                    'error' => $e->getMessage(),
                ]);
            }
        }

        try {
            app(AchievementService::class)->checkAndAward($agent, 'extract');
        } catch (\Throwable $e) {
            // Achievement check must never break the main operation
        }

        return response()->json([
            'data' => $created,
            'meta' => [
                'extracted_count' => count($extracted),
                'stored_count' => count($created),
            ],
        ], 201);
    }

    /**
     * Resolve the active agent (same logic as MemoryController).
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
}
