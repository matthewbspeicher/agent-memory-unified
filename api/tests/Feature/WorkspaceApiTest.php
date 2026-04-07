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
        $owner = makeOwner();
        $agent = makeAgent($owner);

        $response = $this->postJson('/api/v1/workspaces', [
            'name' => 'Project Alpha',
            'description' => 'A top secret project',
        ], withAgent($agent));

        $response->assertCreated()
            ->assertJsonFragment([
                'name' => 'Project Alpha',
                'description' => 'A top secret project',
            ]);

        $workspace = Workspace::first();
        expect($workspace->owner_id)->toBe($owner->id);
        expect($agent->workspaces()->count())->toBe(1);
    });

    it('allows an agent to create a guild workspace', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner);

        $response = $this->postJson('/api/v1/workspaces', [
            'name' => 'The Logic Order',
            'description' => 'A guild for logic lovers',
            'is_guild' => true,
        ], withAgent($agent));

        $response->assertCreated()
            ->assertJsonFragment([
                'name' => 'The Logic Order',
                'is_guild' => true,
                'guild_elo' => 1000,
            ]);
    });

    it('allows an agent to list their workspaces', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner);

        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);
        $agent->workspaces()->attach($workspace->id);

        $response = $this->getJson('/api/v1/workspaces', withAgent($agent));

        $response->assertOk();
        expect($response->json('data'))->toHaveCount(1);
        expect($response->json('data.0.name'))->toBe($workspace->name);
    });

    it('allows an agent with the same owner to join a workspace', function () {
        $owner = makeOwner();

        $creator = makeAgent($owner);
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);
        $creator->workspaces()->attach($workspace->id);

        $joiner = makeAgent($owner);

        $response = $this->postJson("/api/v1/workspaces/{$workspace->id}/join", [], withAgent($joiner));

        $response->assertOk();
        expect($joiner->workspaces()->count())->toBe(1);
    });

    it('prevents agents from different owners from joining a workspace', function () {
        $owner1 = makeOwner();
        $owner2 = makeOwner();

        $workspace = Workspace::factory()->create(['owner_id' => $owner1->id]);

        $joiner = makeAgent($owner2);

        $response = $this->postJson("/api/v1/workspaces/{$workspace->id}/join", [], withAgent($joiner));

        $response->assertForbidden();
        expect($joiner->workspaces()->count())->toBe(0);
    });

    it('allows an agent to publish a memory to a workspace', function () {
        $mock = Mockery::mock(\App\Contracts\EmbeddingServiceInterface::class);
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        app()->instance(\App\Contracts\EmbeddingServiceInterface::class, $mock);

        $owner = makeOwner();
        $agent = makeAgent($owner);

        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);
        $agent->workspaces()->attach($workspace->id);

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'This is a workspace thought',
            'visibility' => 'workspace',
            'workspace_id' => $workspace->id,
        ], withAgent($agent));

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
        $this->mock(\App\Contracts\EmbeddingServiceInterface::class, function ($mock) {
            $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        });

        $owner = makeOwner();

        $author = makeAgent($owner);
        $searcher = makeAgent($owner);

        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);
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
        $response = $this->getJson('/api/v1/memories/search?q=brilliant', withAgent($searcher));

        $response->assertOk();
        $data = $response->json('data');
        expect($data)->toHaveCount(1);
        expect($data[0]['key'])->toBe('shared-thought');
    });
});
