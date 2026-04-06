<?php

namespace App\Http\Controllers\Api;

use App\Concerns\FormatsMemories;
use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Services\AchievementService;
use App\Services\MemoryService;
use App\Services\SummarizationService;
use App\Traits\ResolvesAgent;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class SessionController extends Controller
{
    use FormatsMemories;
    use ResolvesAgent;

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

    // resolveAgent() provided by ResolvesAgent trait
}
