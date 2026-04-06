<?php

namespace Tests\Feature;

use App\Models\Agent;
use App\Models\ArenaChallenge;
use App\Models\ArenaGym;
use App\Models\ArenaSession;
use App\Models\User;
use App\Services\BattleArenaService;
use App\Services\SummarizationService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;
use Mockery;

class BattleArenaServiceTest extends TestCase
{
    use RefreshDatabase;

    private BattleArenaService $service;
    private $summarizationServiceMock;

    protected function setUp(): void
    {
        parent::setUp();

        $this->summarizationServiceMock = Mockery::mock(SummarizationService::class);
        $this->app->instance(SummarizationService::class, $this->summarizationServiceMock);
        
        $this->service = app(BattleArenaService::class);
    }

    public function test_can_start_session()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);
        $gym = ArenaGym::create(['name' => 'Logic Gym', 'owner_id' => $user->id]);
        $challenge = ArenaChallenge::create([
            'gym_id' => $gym->id,
            'title' => 'Logic Test',
            'prompt' => 'Solve 2+2',
            'difficulty_level' => 'easy',
            'xp_reward' => 100,
            'validator_type' => 'llm'
        ]);

        $session = $this->service->startSession($agent, $challenge);

        $this->assertInstanceOf(ArenaSession::class, $session);
        $this->assertEquals($agent->id, $session->agent_id);
        $this->assertEquals($challenge->id, $session->challenge_id);
        $this->assertEquals('in_progress', $session->status);
    }

    public function test_can_submit_turn_with_judging()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);
        $gym = ArenaGym::create(['name' => 'Logic Gym', 'owner_id' => $user->id]);
        $challenge = ArenaChallenge::create([
            'gym_id' => $gym->id,
            'title' => 'Logic Test',
            'prompt' => 'Solve 2+2',
            'difficulty_level' => 'easy',
            'xp_reward' => 100,
            'validator_type' => 'llm'
        ]);

        $session = $this->service->startSession($agent, $challenge);

        // Mock the LLM response for judging
        $this->summarizationServiceMock->shouldReceive('callGemini')
            ->once()
            ->andReturn(json_encode([
                'score' => 95,
                'feedback' => 'Excellent work.',
                'is_final' => true
            ]));

        $turn = $this->service->submitTurn($session, 'The answer is 4');

        $this->assertEquals(95, $turn->validator_response['score']);
        $this->assertEquals('Excellent work.', $turn->validator_response['feedback']);
        $this->assertEquals('completed', $session->fresh()->status);
        $this->assertEquals(95, $session->fresh()->score);
        
        // Verify rewards (XP) — must refresh to avoid stale relationship cache
        $agent->refresh();
        $this->assertEquals(95, $agent->arenaProfile->xp);
        // ELO should increment by 5 for score >= 80
        $this->assertEquals(1005, $agent->arenaProfile->global_elo);
    }

    public function test_can_execute_match_between_agents()
    {
        $user = User::factory()->create();
        $agent1 = Agent::factory()->create(['owner_id' => $user->id, 'name' => 'Agent 1']);
        $agent2 = Agent::factory()->create(['owner_id' => $user->id, 'name' => 'Agent 2']);
        
        $gym = ArenaGym::create(['name' => 'Battle Ground', 'owner_id' => $user->id]);
        $challenge = ArenaChallenge::create([
            'gym_id' => $gym->id,
            'title' => 'Combat',
            'prompt' => 'Fight!',
            'difficulty_level' => 'medium',
            'xp_reward' => 500,
            'validator_type' => 'llm'
        ]);

        $match = $this->service->executeMatch($agent1, $agent2, $challenge);

        $this->assertNotNull($match->winner_id);
        $this->assertEquals('completed', $match->status);
        
        $this->assertDatabaseHas('arena_sessions', [
            'match_id' => $match->id,
            'agent_id' => $agent1->id
        ]);
        
        $this->assertDatabaseHas('arena_sessions', [
            'match_id' => $match->id,
            'agent_id' => $agent2->id
        ]);

        // Verify ELOs updated
        $this->assertNotEquals(1000, $agent1->fresh()->arenaProfile->global_elo);
        $this->assertNotEquals(1000, $agent2->fresh()->arenaProfile->global_elo);
    }
}
