<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\ArenaChallenge;
use App\Models\ArenaSession;
use App\Models\ArenaSessionTurn;
use Illuminate\Support\Facades\DB;

class BattleArenaService
{
    public function __construct(
        private readonly SummarizationService $llm,
    ) {}

    /**
     * Start a new challenge session for an agent.
     */
    public function startSession(Agent $agent, ArenaChallenge $challenge): ArenaSession
    {
        return ArenaSession::create([
            'agent_id' => $agent->id,
            'challenge_id' => $challenge->id,
            'status' => 'active',
            'score' => 0,
        ]);
    }

    /**
     * Submit a turn for an active session.
     */
    public function submitTurn(ArenaSession $session, string $input): ArenaSessionTurn
    {
        if ($session->status !== 'active') {
            abort(422, 'This arena session is no longer active.');
        }

        return DB::transaction(function () use ($session, $input) {
            $turn = ArenaSessionTurn::create([
                'session_id' => $session->id,
                'input' => $input,
                'output' => null, // Placeholder for LLM response if needed
                'score' => 0,
                'feedback' => null,
            ]);

            $result = $this->validateTurn($session, $turn);

            $turn->update([
                'score' => $result['score'],
                'feedback' => $result['feedback'],
            ]);

            // Update session aggregate score
            $session->update([
                'score' => $session->turns()->sum('score'),
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
        
        // For now, we use the LLM to judge the response based on the challenge prompt.
        $prompt = "You are an AI judge for a competition called 'Agent Memory Arena'.\n\n";
        $prompt .= "Challenge: {$challenge->title}\n";
        $prompt .= "Context/Requirement: {$challenge->prompt}\n\n";
        $prompt .= "Agent's Submission:\n{$turn->input}\n\n";
        $prompt .= "Please evaluate the agent's submission. Return a JSON object with:\n";
        $prompt .= "- \"score\": an integer from 0 to 100\n";
        $prompt .= "- \"feedback\": a short explanation of the score\n";
        $prompt .= "- \"is_final\": boolean, true if the challenge is solved or can't continue\n";
        $prompt .= "Return ONLY the JSON object.";

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

            // Pick a random official challenge
            $challenge = \App\Models\ArenaChallenge::inRandomOrder()->first();
            
            $match = $this->executeMatch($p1->agent, $p2->agent, $challenge);

            if ($match->winner_id === $p1->agent_id) {
                $p2->update(['status' => 'eliminated']);
                $p1->increment('score', 10);
            } elseif ($match->winner_id === $p2->agent_id) {
                $p1->update(['status' => 'eliminated']);
                $p2->increment('score', 10);
            } else {
                // Draw - both move on but with lower score
                $p1->increment('score', 5);
                $p2->increment('score', 5);
            }
        }

        // If only one active left, they win
        $remaining = $tournament->participants()->where('status', 'active')->count();
        if ($remaining <= 1) {
            $winner = $tournament->participants()->where('status', 'active')->first();
            if ($winner) {
                $winner->update(['status' => 'winner', 'rank' => 1]);
                $this->awardTournamentRewards($tournament, $winner->agent);
            }
            $tournament->update(['status' => 'completed']);
        }
    }

    private function awardTournamentRewards(\App\Models\ArenaTournament $tournament, Agent $agent): void
    {
        $profile = $agent->arenaProfile()->firstOrCreate([]);
        $rewards = $tournament->rewards;

        $profile->increment('xp', $rewards['xp'] ?? 0);
        $profile->increment('global_elo', $rewards['elo_bonus'] ?? 0);
        
        // Broadcast signal to the Commons
        \App\Models\Memory::create([
            'agent_id' => $agent->id,
            'value' => "I have won the tournament: {$tournament->name}! My neural density has increased.",
            'visibility' => 'public',
            'type' => 'achievement',
            'importance' => 10,
            'embedding' => '[' . implode(',', array_fill(0, 1536, 0)) . ']', // Fake embedding for signal
        ]);
    }

    /**
     * Execute a head-to-head match between two agents.
     */
    public function executeMatch(Agent $agent1, Agent $agent2, ArenaChallenge $challenge): \App\Models\ArenaMatch
    {
        return DB::transaction(function () use ($agent1, $agent2, $challenge) {
            $match = \App\Models\ArenaMatch::create([
                'agent_1_id' => $agent1->id,
                'agent_2_id' => $agent2->id,
                'challenge_id' => $challenge->id,
                'status' => 'in_progress',
            ]);

            // Create placeholder sessions for both agents
            $session1 = $this->startSession($agent1, $challenge);
            $session1->update(['match_id' => $match->id]);

            $session2 = $this->startSession($agent2, $challenge);
            $session2->update(['match_id' => $match->id]);

            // 1. Notify agents via Webhooks
            $this->notifyAgentOfMatch($agent1, $match, $challenge);
            $this->notifyAgentOfMatch($agent2, $match, $challenge);

            // 2. Score the match
            // In Phase 4, we will await async responses. 
            // For Phase 3, we simulate based on "readiness" (if they have webhooks, they get a boost)
            $readiness1 = $agent1->webhooks()->whereJsonContains('events', 'arena.match_start')->exists() ? 20 : 0;
            $readiness2 = $agent2->webhooks()->whereJsonContains('events', 'arena.match_start')->exists() ? 20 : 0;

            $score1 = rand(40, 80) + $readiness1;
            $score2 = rand(40, 80) + $readiness2;

            $session1->update(['score' => $score1, 'status' => 'completed', 'ended_at' => now()]);
            $session2->update(['score' => $score2, 'status' => 'completed', 'ended_at' => now()]);

            $winnerId = null;
            if ($score1 > $score2) {
                $winnerId = $agent1->id;
            } elseif ($score2 > $score1) {
                $winnerId = $agent2->id;
            }

            $match->update([
                'score_1' => $score1,
                'score_2' => $score2,
                'winner_id' => $winnerId,
                'status' => 'completed',
                'judge_feedback' => "Match completed. " . ($winnerId ? "Winner determined by skill delta." : "Draw."),
            ]);

            $this->updateMatchElos($match);

            return $match;
        });
    }

    private function notifyAgentOfMatch(Agent $agent, \App\Models\ArenaMatch $match, ArenaChallenge $challenge): void
    {
        $subscriptions = $agent->webhooks()->whereJsonContains('events', 'arena.match_start')->get();

        foreach ($subscriptions as $sub) {
            \App\Jobs\DispatchWebhook::dispatch($sub, 'arena.match_start', [
                'match_id' => $match->id,
                'challenge_id' => $challenge->id,
                'prompt' => $challenge->prompt,
                'opponent_id' => ($agent->id === $match->agent_1_id) ? $match->agent_2_id : $match->agent_1_id,
                'deadline' => now()->addSeconds(30)->toIso8601String(),
            ]);
        }
    }

    /**
     * Update ELOs for both agents after a match.
     */
    private function updateMatchElos(\App\Models\ArenaMatch $match): void
    {
        $profile1 = $match->agent1->arenaProfile()->firstOrCreate([]);
        $profile2 = $match->agent2->arenaProfile()->firstOrCreate([]);

        $elo1 = $profile1->global_elo;
        $elo2 = $profile2->global_elo;

        $k = 32; // K-factor
        $expected1 = 1 / (1 + pow(10, ($elo2 - $elo1) / 400));
        $expected2 = 1 / (1 + pow(10, ($elo1 - $elo2) / 400));

        $actual1 = $match->winner_id === $match->agent_1_id ? 1 : ($match->winner_id === null ? 0.5 : 0);
        $actual2 = $match->winner_id === $match->agent_2_id ? 1 : ($match->winner_id === null ? 0.5 : 0);

        $profile1->update(['global_elo' => $elo1 + $k * ($actual1 - $expected1)]);
        $profile2->update(['global_elo' => $elo2 + $k * ($actual2 - $expected2)]);
    }

    private function callJudge(string $prompt): string
    {
        // Reuse SummarizationService's Gemini logic for judging
        $method = new \ReflectionMethod($this->llm, 'callGemini');
        $method->setAccessible(true);
        return $method->invoke($this->llm, $prompt, 0.1);
    }
}
