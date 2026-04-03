<?php

use App\Models\Memory;
use App\Models\WebhookSubscription;
use App\Models\Workspace;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        $mock->shouldReceive('embedBatch')->andReturn([array_fill(0, 1536, 0.1)]);
    });
});

describe('Cross-tenant memory isolation', function () {
    it('agent B cannot read agent A private memory', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner);
        $agentB = makeAgent($owner);

        Memory::factory()->create([
            'agent_id' => $agentA->id,
            'key' => 'secret',
            'visibility' => 'private',
        ]);

        $this->getJson('/api/v1/memories/secret', withAgent($agentB))
            ->assertNotFound();
    });

    it('agent B cannot update agent A memory', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner);
        $agentB = makeAgent($owner);

        Memory::factory()->create([
            'agent_id' => $agentA->id,
            'key' => 'secret',
            'visibility' => 'private',
        ]);

        $this->patchJson('/api/v1/memories/secret', [
            'value' => 'hacked',
        ], withAgent($agentB))
            ->assertNotFound();
    });

    it('agent B cannot delete agent A memory', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner);
        $agentB = makeAgent($owner);

        Memory::factory()->create([
            'agent_id' => $agentA->id,
            'key' => 'secret',
            'visibility' => 'private',
        ]);

        $this->deleteJson('/api/v1/memories/secret', [], withAgent($agentB))
            ->assertNotFound();
    });

    it('agent cannot create relations to another agent private memory', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner);
        $agentB = makeAgent($owner);

        $privateMemory = Memory::factory()->create([
            'agent_id' => $agentA->id,
            'visibility' => 'private',
        ]);

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'trying to link to private memory',
            'relations' => [
                ['id' => $privateMemory->id, 'type' => 'related'],
            ],
        ], withAgent($agentB));

        $response->assertUnprocessable();
    });

    it('agent cannot store memory in workspace it does not belong to', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner);
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);
        // Note: agentA is NOT added to the workspace

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'trying to inject into workspace',
            'visibility' => 'workspace',
            'workspace_id' => $workspace->id,
        ], withAgent($agentA));

        // Either 422 (validation blocks it) or 403 (plan limits block it for free users)
        expect($response->status())->toBeIn([403, 422]);
    });

    it('agent B cannot delete agent A webhook', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner);
        $agentB = makeAgent($owner);

        $webhook = WebhookSubscription::factory()->create([
            'agent_id' => $agentA->id,
        ]);

        $this->deleteJson("/api/v1/webhooks/{$webhook->id}", [], withAgent($agentB))
            ->assertNotFound();
    });
});
