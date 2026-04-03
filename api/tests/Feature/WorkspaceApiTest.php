<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Models\Workspace;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

describe('Workspaces API', function () {
    it('allows an agent to create a workspace and auto-joins them', function () {
        $user = User::factory()->create(['stripe_id' => 'cus_test_ws1']);
        $sub = $user->subscriptions()->create([
            'type' => 'default',
            'stripe_id' => 'sub_test_ws1',
            'stripe_status' => 'active',
            'stripe_price' => 'price_test',
            'quantity' => 1,
        ]);
        $sub->items()->create(['stripe_id' => 'si_test_ws1', 'stripe_product' => 'prod_test', 'stripe_price' => 'price_test', 'quantity' => 1]);
        $user = $user->fresh();

        $agent = Agent::factory()->create(['owner_id' => $user->id]);
        $token = 'amc_test_token';
        $agent->update(['api_token' => $token]);

        $response = $this->withToken($token)->postJson('/api/v1/workspaces', [
            'name' => 'Project Alpha',
            'description' => 'A top secret project',
        ]);

        $response->assertCreated()
            ->assertJsonFragment([
                'name' => 'Project Alpha',
                'description' => 'A top secret project',
            ]);

        $workspace = Workspace::first();
        expect($workspace->owner_id)->toBe($user->id);

        expect($agent->workspaces()->count())->toBe(1);
        expect($agent->workspaces()->first()->id)->toBe($workspace->id);
    });

    it('allows an agent to create a guild workspace', function () {
        $user = User::factory()->create(['stripe_id' => 'cus_test_ws2']);
        $sub = $user->subscriptions()->create([
            'type' => 'default',
            'stripe_id' => 'sub_test_ws2',
            'stripe_status' => 'active',
            'stripe_price' => 'price_test',
            'quantity' => 1,
        ]);
        $sub->items()->create(['stripe_id' => 'si_test_ws2', 'stripe_product' => 'prod_test', 'stripe_price' => 'price_test', 'quantity' => 1]);
        $user = $user->fresh();

        $agent = Agent::factory()->create(['owner_id' => $user->id]);
        $token = 'amc_test_token';
        $agent->update(['api_token' => $token]);

        $response = $this->withToken($token)->postJson('/api/v1/workspaces', [
            'name' => 'The Logic Order',
            'description' => 'A guild for logic lovers',
            'is_guild' => true,
        ]);

        $response->assertCreated()
            ->assertJsonFragment([
                'name' => 'The Logic Order',
                'is_guild' => true,
                'guild_elo' => 1000,
            ]);
    });

    it('allows an agent to list their workspaces', function () {
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);
        $token = 'amc_test_token';
        $agent->update(['api_token' => $token]);

        $workspace = Workspace::factory()->create(['owner_id' => $user->id]);
        $agent->workspaces()->attach($workspace->id);

        $response = $this->withToken($token)->getJson('/api/v1/workspaces');

        $response->assertOk();
        expect($response->json('data'))->toHaveCount(1);
        expect($response->json('data.0.name'))->toBe($workspace->name);
    });

    it('allows an agent with the same owner to join a workspace', function () {
        $user = User::factory()->create();

        $creator = Agent::factory()->create(['owner_id' => $user->id]);
        $workspace = Workspace::factory()->create(['owner_id' => $user->id]);
        $creator->workspaces()->attach($workspace->id);

        $joiner = Agent::factory()->create(['owner_id' => $user->id]);
        $token = 'amc_test_token';
        $joiner->update(['api_token' => $token]);

        $response = $this->withToken($token)->postJson("/api/v1/workspaces/{$workspace->id}/join");

        $response->assertOk();
        expect($joiner->workspaces()->count())->toBe(1);
    });

    it('prevents agents from different owners from joining a workspace', function () {
        $user1 = User::factory()->create();
        $user2 = User::factory()->create();

        $workspace = Workspace::factory()->create(['owner_id' => $user1->id]);

        $joiner = Agent::factory()->create(['owner_id' => $user2->id]);
        $token = 'amc_test_token';
        $joiner->update(['api_token' => $token]);

        $response = $this->withToken($token)->postJson("/api/v1/workspaces/{$workspace->id}/join");

        $response->assertForbidden();
        expect($joiner->workspaces()->count())->toBe(0);
    });

    it('allows an agent to publish a memory to a workspace', function () {
        $mock = Mockery::mock(EmbeddingService::class);
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        app()->instance(EmbeddingService::class, $mock);

        $user = User::factory()->create(['stripe_id' => 'cus_test_wp1']);
        $sub = $user->subscriptions()->create([
            'type' => 'default',
            'stripe_id' => 'sub_test_wp1',
            'stripe_status' => 'active',
            'stripe_price' => 'price_test',
            'quantity' => 1,
        ]);
        $sub->items()->create(['stripe_id' => 'si_test_wp1', 'stripe_product' => 'prod_test', 'stripe_price' => 'price_test', 'quantity' => 1]);
        $user = $user->fresh();

        $agent = Agent::factory()->create(['owner_id' => $user->id]);
        $token = 'amc_test_token';
        $agent->update(['api_token' => $token]);

        $workspace = Workspace::factory()->create(['owner_id' => $user->id]);
        $agent->workspaces()->attach($workspace->id);

        $response = $this->withToken($token)->postJson('/api/v1/memories', [
            'value' => 'This is a workspace thought',
            'visibility' => 'workspace',
            'workspace_id' => $workspace->id,
        ]);

        $response->assertCreated();
        $response->assertJsonFragment([
            'visibility' => 'workspace',
            'workspace_id' => $workspace->id,
        ]);

        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'workspace_id' => $workspace->id,
            'visibility' => 'workspace',
        ]);
    });

    it('allows an agent to search and retrieve memories from their workspaces', function () {
        $this->mock(EmbeddingService::class, function ($mock) {
            $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        });

        $user = User::factory()->create();

        $author = Agent::factory()->create(['owner_id' => $user->id]);
        $searcher = Agent::factory()->create(['owner_id' => $user->id]);
        $token = 'amc_test_token';
        $searcher->update(['api_token' => $token]);

        $workspace = Workspace::factory()->create(['owner_id' => $user->id]);
        $author->workspaces()->attach($workspace->id);
        $searcher->workspaces()->attach($workspace->id);

        $vector = array_fill(0, 1536, 0.1);

        // Author creates a memory in the workspace
        Memory::create([
            'agent_id' => $author->id,
            'workspace_id' => $workspace->id,
            'key' => 'shared-thought',
            'value' => 'This is a brilliant idea shared in the workspace.',
            'embedding' => '['.implode(',', $vector).']',
            'visibility' => 'workspace',
        ]);

        // Searcher should be able to find it
        $response = $this->withToken($token)->getJson('/api/v1/memories/search?q=brilliant');

        $response->assertOk();
        $data = $response->json('data');
        expect($data)->toHaveCount(1);
        expect($data[0]['key'])->toBe('shared-thought');
    });
});
