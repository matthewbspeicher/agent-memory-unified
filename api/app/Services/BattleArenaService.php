<?php

namespace App\Services;

use App\Contracts\SummarizationServiceInterface;
use App\Models\Agent;
use App\Models\ArenaChallenge;
use App\Models\ArenaSession;
use App\Models\ArenaSessionTurn;
use Illuminate\Support\Facades\DB;

class BattleArenaService
{
    public function __construct(
        private readonly SummarizationServiceInterface $llm,
    ) {}

    /**
     * Start a new challenge session for an agent.
     */
    public function startSession(Agent $agent, ArenaChallenge $challenge): ArenaSession
    {
        return ArenaSession::create([
            'agent_id' => $agent->id,
            'challenge_id' => $challenge->id,
            'status' => 'in_progress', // Match migration default
            'score' => 0,
        ]);
    }

    /**
     * Submit a turn for an active session.
     */
    public function submitTurn(ArenaSession $session, string $input): ArenaSessionTurn
    {
        if (!in_array($session->status, ['in_progress', 'active'])) {
            abort(422, 'This arena session is no longer active.');
        }

        $turnNumber = $session->turns()->count() + 1;

        $turn = ArenaSessionTurn::create([
            'session_id' => $session->id,
            'turn_number' => $turnNumber,
            'agent_payload' => ['input' => $input],
            'validator_response' => null,
        ]);

        $result = $this->validateTurn($session, $turn);

        return DB::transaction(function () use ($session, $turn, $result) {
            $turn->update([
                'validator_response' => $result,
            ]);

            // Update session aggregate score
            $totalScore = DB::table('arena_session_turns')
                ->where('session_id', $session->id)
                ->whereNotNull('validator_response')
                ->get()
                ->sum(function ($t) {
                    $val = json_decode($t->validator_response, true);
                    return $val['score'] ?? 0;
                });

            $session->update([
                'score' => $totalScore,
            ]);

            // If it's a single-turn challenge or the validator says it's done, end the session
            if ($result['is_final'] ?? true) {
                $session->update([
                    'status' => 'completed',
                    'ended_at' => now(),
                ]);
                
                $this->awardRewards($session);
            }

            return $turn;
        });
    }

    /**
     * Validate a turn using the challenge's validator configuration.
     */
    private function validateTurn(ArenaSession $session, ArenaSessionTurn $turn): array
    {
        $challenge = $session->challenge;
        $input = $turn->agent_payload['input'] ?? '';
        
        // For now, we use the LLM to judge the response based on the challenge prompt.
        $prompt = view('prompts.arena-judge', compact('challenge', 'input'))->render();

        try {
            $raw = $this->callJudge($prompt);
            $parsed = json_decode($raw, true);
            
            return [
                'score' => (int) ($parsed['score'] ?? 0),
                'feedback' => $parsed['feedback'] ?? 'No feedback provided.',
                'is_final' => (bool) ($parsed['is_final'] ?? true),
            ];
        } catch (\Exception $e) {
            return [
                'score' => 0,
                'feedback' => 'Validation error: ' . $e->getMessage(),
                'is_final' => true,
            ];
        }
    }

    /**
     * Award XP and updates ELO based on session outcome.
     */
    private function awardRewards(ArenaSession $session): void
    {
        $agent = $session->agent;
        $challenge = $session->challenge;

        $profile = $agent->arenaProfile()->firstOrCreate([]);

        // Basic XP reward scaled by score
        $xpEarned = (int) ($challenge->xp_reward * ($session->score / 100));
        $profile->increment('xp', $xpEarned);

        // Simple Gym ELO adjustment
        if ($session->score >= 80) {
            $profile->increment('global_elo', 5);
        } elseif ($session->score < 20) {
            $profile->decrement('global_elo', 2);
        }
    }

    /**
     * Find a suitable opponent for an agent based on ELO.
     */
    public function findOpponent(Agent $agent): ?Agent
    {
        $profile = $agent->arenaProfile()->firstOrCreate([]);
        $myElo = $profile->global_elo;

        return Agent::where('id', '!=', $agent->id)
            ->where('is_active', true)
            ->whereHas('arenaProfile', function ($query) use ($myElo) {
                $query->whereBetween('global_elo', [$myElo - 200, $myElo + 200]);
            })
            ->inRandomOrder()
            ->first();
    }

    /**
     * Execute a simulated match between two agents.
     */
    public function executeMatch(Agent $agent1, Agent $agent2, ArenaChallenge $challenge): \App\Models\ArenaMatch
    {
        $match = \App\Models\ArenaMatch::create([
            'challenge_id' => $challenge->id,
            'agent_1_id' => $agent1->id,
            'agent_2_id' => $agent2->id,
            'status' => 'in_progress',
        ]);

        // Start sessions for both
        $s1 = $this->startSession($agent1, $challenge);
        $s2 = $this->startSession($agent2, $challenge);
        
        $s1->update(['match_id' => $match->id]);
        $s2->update(['match_id' => $match->id]);

        // Generate simulated submissions for each agent and judge them
        $submission1 = "Agent '{$agent1->name}' (capabilities: " . implode(', ', $agent1->scopes ?? ['general']) . ") "
            . "attempts challenge: {$challenge->prompt}";
        $submission2 = "Agent '{$agent2->name}' (capabilities: " . implode(', ', $agent2->scopes ?? ['general']) . ") "
            . "attempts challenge: {$challenge->prompt}";

        // Judge each agent's simulated turn
        $result1 = $this->judgeMatchTurn($s1, $challenge, $submission1);
        $result2 = $this->judgeMatchTurn($s2, $challenge, $submission2);

        $score1 = $result1['score'];
        $score2 = $result2['score'];

        $s1->update(['score' => $score1, 'status' => 'completed', 'ended_at' => now()]);
        $s2->update(['score' => $score2, 'status' => 'completed', 'ended_at' => now()]);

        $winnerId = $score1 >= $score2 ? $agent1->id : $agent2->id;

        // Build comparative judge feedback
        $judgeFeedback = "Agent 1 ({$agent1->name}): {$result1['feedback']} | "
            . "Agent 2 ({$agent2->name}): {$result2['feedback']}";

        $match->update([
            'status' => 'completed',
            'winner_id' => $winnerId,
            'score_1' => $score1,
            'score_2' => $score2,
            'judge_feedback' => $judgeFeedback,
        ]);

        $this->updateMatchElos($match);

        return $match;
    }

    /**
     * Judge a single agent's turn in a head-to-head match.
     */
    private function judgeMatchTurn(ArenaSession $session, ArenaChallenge $challenge, string $submission): array
    {
        $turn = ArenaSessionTurn::create([
            'session_id' => $session->id,
            'turn_number' => 1,
            'agent_payload' => ['input' => $submission],
            'validator_response' => null,
        ]);

        $result = $this->validateTurn($session, $turn);

        $turn->update(['validator_response' => $result]);

        return $result;
    }

    private function updateMatchElos(\App\Models\ArenaMatch $match): void
    {
        $a1 = $match->agent1->arenaProfile()->firstOrCreate([]);
        $a2 = $match->agent2->arenaProfile()->firstOrCreate([]);

        if ($match->winner_id === $match->agent_1_id) {
            $a1->increment('global_elo', 15);
            $a2->decrement('global_elo', 10);
        } else {
            $a2->increment('global_elo', 15);
            $a1->decrement('global_elo', 10);
        }
    }

    /**
     * TOURNAMENT ENGINE
     */

    public function createDailyTournament(): \App\Models\ArenaTournament
    {
        return \App\Models\ArenaTournament::create([
            'name' => 'The Daily Neural Circuit - ' . now()->format('Y-m-d'),
            'type' => 'daily',
            'status' => 'open',
            'starts_at' => now()->addHours(1),
            'ends_at' => now()->addHours(4),
            'rewards' => [
                'xp' => 1000,
                'elo_bonus' => 50,
                'badges' => ['circuit_winner'],
            ],
        ]);
    }

    public function joinTournament(\App\Models\ArenaTournament $tournament, Agent $agent): void
    {
        if ($tournament->status !== 'open') {
            abort(422, 'Tournament is not open for registration.');
        }

        $agent->arenaTournaments()->syncWithoutDetaching([$tournament->id]);
    }

    public function processTournamentRound(\App\Models\ArenaTournament $tournament): void
    {
        $tournament->update(['status' => 'in_progress']);

        $participants = $tournament->participants()->where('status', 'active')->get();
        
        if ($participants->count() < 2) {
            $tournament->update(['status' => 'completed']);
            return;
        }

        // Simple single-elimination bracket logic
        $pairs = $participants->shuffle()->chunk(2);

        foreach ($pairs as $pair) {
            if ($pair->count() < 2) {
                // Odd one out gets a bye to next round
                continue;
            }

            $p1 = $pair->first();
            $p2 = $pair->last();
            
            // For now, tournaments use a generic high-stakes logic challenge
            $challenge = ArenaChallenge::where('difficulty_level', 'hard')->first() 
                ?? ArenaChallenge::first();

            if ($challenge) {
                \App\Jobs\ExecuteArenaMatchJob::dispatch($p1, $p2, $challenge);
            }
        }
    }

    private function callJudge(string $prompt): string
    {
        return $this->llm->callGemini($prompt, 0.1);
    }
}
