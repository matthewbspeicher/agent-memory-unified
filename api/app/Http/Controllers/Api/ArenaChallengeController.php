<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\ArenaChallenge;
use App\Models\ArenaSession;
use App\Services\BattleArenaService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ArenaChallengeController extends Controller
{
    public function __construct(
        private readonly BattleArenaService $arena,
    ) {}

    /**
     * Start a new challenge session.
     * POST /v1/arena/challenges/{id}/start
     */
    public function start(Request $request, string $id): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $challenge = ArenaChallenge::findOrFail($id);

        $session = $this->arena->startSession($agent, $challenge);

        return response()->json([
            'message' => 'Arena session started.',
            'data' => [
                'session_id' => $session->id,
                'challenge' => [
                    'title' => $challenge->title,
                    'prompt' => $challenge->prompt,
                ],
            ],
        ], 201);
    }

    /**
     * Submit an answer or move for a session.
     * POST /v1/arena/sessions/{sessionId}/submit
     */
    public function submit(Request $request, string $sessionId): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $session = ArenaSession::where('agent_id', $agent->id)
            ->findOrFail($sessionId);

        $validated = $request->validate([
            'input' => ['required', 'string', 'max:5000'],
        ]);

        $turn = $this->arena->submitTurn($session, $validated['input']);

        return response()->json([
            'data' => [
                'turn_id' => $turn->id,
                'score' => $turn->score,
                'feedback' => $turn->feedback,
                'session_status' => $session->fresh()->status,
                'total_score' => $session->fresh()->score,
            ],
        ]);
    }
}
