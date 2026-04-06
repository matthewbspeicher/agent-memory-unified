<?php

use App\Models\User;
use App\Models\Workspace;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Str;

uses(RefreshDatabase::class);

// ---------------------------------------------------------------------------
// Plan Helper Tests (Simplified Model — all users are effectively Pro)
// ---------------------------------------------------------------------------

describe('plan helpers', function () {
    it('returns true for isPro for all users', function () {
        $user = makeOwner();
        expect($user->isPro())->toBeTrue();
    });

    it('returns PHP_INT_MAX max agents for all users', function () {
        $user = makeOwner();
        expect($user->maxAgents())->toBe(PHP_INT_MAX);
    });

    it('returns true for hasUnlimitedAgentAccess', function () {
        $user = makeOwner();
        expect($user->hasUnlimitedAgentAccess())->toBeTrue();
    });

    it('returns 100000 max memories per agent', function () {
        $user = makeOwner();
        expect($user->maxMemoriesPerAgent())->toBe(100_000);
    });

    it('returns true for canCreateWorkspace for all users', function () {
        $user = makeOwner();
        expect($user->canCreateWorkspace())->toBeTrue();
    });

    it('returns false for isDowngraded for all users', function () {
        $user = makeOwner();
        expect($user->isDowngraded())->toBeFalse();
    });

    it('returns false for isOnGracePeriod for all users', function () {
        $user = makeOwner();
        expect($user->isOnGracePeriod())->toBeFalse();
    });

    it('returns false for hasPaymentFailure for all users', function () {
        $user = makeOwner();
        expect($user->hasPaymentFailure())->toBeFalse();
    });
});

// ---------------------------------------------------------------------------
// Agent Registration (No Cap in Simplified Model)
// ---------------------------------------------------------------------------

describe('agent creation', function () {
    it('allows user to register agents via API without limit', function () {
        $owner = makeOwner();
        for ($i = 0; $i < 6; $i++) {
            $response = $this->postJson('/api/v1/agents/register', [
                'name' => "Agent $i",
                'owner_token' => $owner->_plaintext_token,
            ]);
            $response->assertStatus(201);
        }
    });
});

// ---------------------------------------------------------------------------
// Workspace Creation (All users can create)
// ---------------------------------------------------------------------------

describe('workspace creation', function () {
    it('allows any user to create workspaces', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner);

        $response = $this->postJson('/api/v1/workspaces', [
            'name' => 'Private Workspace',
        ], withAgent($agent));

        $response->assertStatus(201);
    });
});

// ---------------------------------------------------------------------------
// Write Access (No soft lock in simplified model)
// ---------------------------------------------------------------------------

describe('write access', function () {
    beforeEach(function () {
        $mock = Mockery::mock(EmbeddingService::class);
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        app()->instance(EmbeddingService::class, $mock);
    });

    it('allows write on all agents regardless of count', function () {
        $owner = makeOwner();
        $agents = [];
        for ($i = 0; $i < 6; $i++) {
            $agents[] = makeAgent($owner);
        }

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'test memory',
        ], withAgent($agents[5]));

        $response->assertStatus(201);
    });

    it('allows workspace memory writes for all users', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner);
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);
        $agent->workspaces()->attach($workspace->id);

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'workspace memory',
            'workspace_id' => $workspace->id,
        ], withAgent($agent));

        $response->assertStatus(201);
    });
});

// NOTE: Billing routes (/pricing, /billing/*) removed from application.
// Route tests removed accordingly.

// ---------------------------------------------------------------------------
// Dashboard JSON Props
// ---------------------------------------------------------------------------

describe('dashboard props', function () {
    it('returns agent count and hasApiToken in dashboard JSON', function () {
        $user = makeOwner();
        makeAgent($user);

        $response = $this->actingAs($user)->get('/dashboard');
        $response->assertOk();
        $response->assertJson(fn ($json) => $json
            ->where('hasApiToken', true)
            ->has('agents', 1)
            ->has('agentCount')
            ->has('avgMemoriesPerAgent')
            ->etc()
        );
    });
});
