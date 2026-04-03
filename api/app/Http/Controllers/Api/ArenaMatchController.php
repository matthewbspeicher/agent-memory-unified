<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\ArenaChallenge;
use App\Models\ArenaMatch;
use App\Services\BattleArenaService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ArenaMatchController extends Controller
{
    public function __construct(
        private readonly BattleArenaService $arena,
    ) {}

    /**
     * Request a match against a random opponent.
     * POST /v1/arena/matches/request
     */
    public function requestMatch(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        
        $opponent = $this->arena->findOpponent($agent);
        
        if (!$opponent) {
            return response()->json([
                'error' => 'No suitable opponent found at this time. Try again later.',
            ], 404);
        }

        // Pick a random official challenge for the match
        $challenge = ArenaChallenge::whereHas('gym', function ($q) {
            $q->where('is_official', true);
        })->inRandomOrder()->first();

        if (!$challenge) {
            return response()->json(['error' => 'No challenges available for matchmaking.'], 500);
        }

        $match = $this->arena->executeMatch($agent, $opponent, $challenge);

        return response()->json([
            'message' => 'Match executed.',
            'data' => $match->load(['agent1', 'agent2', 'challenge', 'winner']),
        ]);
    }

    /**
     * List recent matches.
     * GET /v1/arena/matches
     */
    public function index(): JsonResponse
    {
        $matches = ArenaMatch::with(['agent1', 'agent2', 'challenge', 'winner'])
            ->latest()
            ->paginate(20);

        return response()->json($matches);
    }
}
