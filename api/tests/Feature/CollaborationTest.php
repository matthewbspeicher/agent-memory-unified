<?php

use App\Models\CollaborationMention;
use App\Models\Memory;
use App\Models\Workspace;
use App\Models\WorkspaceEvent;
use App\Models\WorkspaceSubscription;
use App\Models\WorkspaceTask;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Str;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')
            ->andReturn(array_fill(0, 1536, 0.1));
        $mock->shouldReceive('embedBatch')
            ->andReturn([array_fill(0, 1536, 0.1)]);
    });
});

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function createWorkspaceWithAgent(): array
{
    $user = makeOwner(['stripe_id' => 'cus_test_'.Str::random(10)]);
    $subscription = $user->subscriptions()->create([
        'type' => 'default',
        'stripe_id' => 'sub_test_'.Str::random(10),
        'stripe_status' => 'active',
        'stripe_price' => config('stripe.pro_price_id') ?: 'price_test',
        'quantity' => 1,
    ]);

    $subscription->items()->create([
        'stripe_id' => 'si_test_'.Str::random(10),
        'stripe_product' => 'prod_test',
        'stripe_price' => config('stripe.pro_price_id') ?: 'price_test',
        'quantity' => 1,
    ]);

    $user = $user->fresh();
    $agent = makeAgent($user);
    $workspace = Workspace::factory()->create(['owner_id' => $user->id]);
    $agent->workspaces()->attach($workspace->id);

    return [$workspace, $agent, $user];
}

// ===========================================================================
// Phase 1: Presence
// ===========================================================================

describe('Presence', function () {
    it('lists workspace presence', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $response = $this->getJson("/api/v1/workspaces/{$workspace->id}/presence", withAgent($agent));

        $response->assertOk();
        expect($response->json('data'))->toBeArray();
    });

    it('shows agent presence', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        // Create presence via heartbeat first
        $this->postJson("/api/v1/workspaces/{$workspace->id}/presence/heartbeat", [], withAgent($agent));

        $response = $this->getJson("/api/v1/workspaces/{$workspace->id}/presence/{$agent->id}", withAgent($agent));

        $response->assertOk();
        expect($response->json('data.agent_id'))->toBe($agent->id);
    });

    it('sends heartbeat', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $response = $this->postJson("/api/v1/workspaces/{$workspace->id}/presence/heartbeat", [], withAgent($agent));

        $response->assertOk();
        expect($response->json('data.status'))->toBe('online');
    });

    it('marks agent offline', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        // Create presence via heartbeat first
        $this->postJson("/api/v1/workspaces/{$workspace->id}/presence/heartbeat", [], withAgent($agent));

        $response = $this->postJson("/api/v1/workspaces/{$workspace->id}/presence/offline", [], withAgent($agent));

        $response->assertOk();
    });

    it('rejects presence for agent not in workspace', function () {
        [$workspace] = createWorkspaceWithAgent();
        $otherUser = makeOwner();
        $otherAgent = makeAgent($otherUser);

        $response = $this->getJson("/api/v1/workspaces/{$workspace->id}/presence", withAgent($otherAgent));

        $response->assertForbidden();
    });
});

// ===========================================================================
// Phase 2: Event Subscriptions
// ===========================================================================

describe('Event Subscriptions', function () {
    it('lists subscriptions', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $response = $this->getJson("/api/v1/workspaces/{$workspace->id}/subscriptions", withAgent($agent));

        $response->assertOk();
        expect($response->json('data'))->toBeArray();
    });

    it('creates a subscription', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $response = $this->postJson("/api/v1/workspaces/{$workspace->id}/subscriptions", [
            'event_types' => ['memory.created', 'task.created'],
        ], withAgent($agent));

        $response->assertCreated();
        expect($response->json('data.event_types'))->toBe(['memory.created', 'task.created']);
        expect($response->json('data.agent_id'))->toBe($agent->id);
    });

    it('updates a subscription', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $sub = WorkspaceSubscription::create([
            'workspace_id' => $workspace->id,
            'agent_id' => $agent->id,
            'event_types' => ['memory.created'],
        ]);

        $response = $this->patchJson("/api/v1/workspaces/{$workspace->id}/subscriptions/{$sub->id}", [
            'event_types' => ['memory.*', 'task.*'],
        ], withAgent($agent));

        $response->assertOk();
        expect($response->json('data.event_types'))->toContain('memory.*');
    });

    it('deletes a subscription', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $sub = WorkspaceSubscription::create([
            'workspace_id' => $workspace->id,
            'agent_id' => $agent->id,
            'event_types' => ['memory.*'],
        ]);

        $response = $this->deleteJson("/api/v1/workspaces/{$workspace->id}/subscriptions/{$sub->id}", [], withAgent($agent));

        $response->assertOk();
        $this->assertDatabaseMissing('workspace_subscriptions', ['id' => $sub->id]);
    });

    it('polls workspace events', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        WorkspaceSubscription::create([
            'workspace_id' => $workspace->id,
            'agent_id' => $agent->id,
            'event_types' => ['*'],
        ]);

        WorkspaceEvent::dispatch($workspace->id, WorkspaceEvent::TYPE_MEMORY_CREATED, $agent->id, [
            'memory_id' => 'test-id',
        ]);

        $response = $this->getJson("/api/v1/workspaces/{$workspace->id}/events", withAgent($agent));

        $response->assertOk();
        expect($response->json('data'))->toHaveCount(1);
    });

    it('filters events by type', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        WorkspaceEvent::dispatch($workspace->id, WorkspaceEvent::TYPE_MEMORY_CREATED, $agent->id, [
            'memory_id' => 'test-id',
        ]);

        WorkspaceEvent::dispatch($workspace->id, WorkspaceEvent::TYPE_TASK_CREATED, $agent->id, [
            'task_id' => 'task-id',
        ]);

        $response = $this->getJson("/api/v1/workspaces/{$workspace->id}/events?event_type=task.created", withAgent($agent));

        $response->assertOk();
        $events = $response->json('data');
        expect($events)->toHaveCount(1);
        expect($events[0]['event_type'])->toBe('task.created');
    });
});

// ===========================================================================
// Phase 3: @Mentions
// ===========================================================================

describe('@Mentions', function () {
    it('lists mentions', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();
        [$otherWorkspace, $otherAgent] = createWorkspaceWithAgent();

        $workspace->agents()->attach($otherAgent->id);

        CollaborationMention::create([
            'workspace_id' => $workspace->id,
            'agent_id' => $agent->id,
            'target_agent_id' => $otherAgent->id,
            'message' => 'Can you help with this?',
        ]);

        $response = $this->getJson("/api/v1/workspaces/{$workspace->id}/mentions", withAgent($otherAgent));

        $response->assertOk();
        expect($response->json('data'))->toHaveCount(1);
    });

    it('lists received mentions', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();
        [$otherWorkspace, $otherAgent] = createWorkspaceWithAgent();

        $workspace->agents()->attach($otherAgent->id);

        CollaborationMention::create([
            'workspace_id' => $workspace->id,
            'agent_id' => $agent->id,
            'target_agent_id' => $otherAgent->id,
            'message' => 'Can you help with this?',
        ]);

        $response = $this->getJson("/api/v1/workspaces/{$workspace->id}/mentions/received", withAgent($otherAgent));

        $response->assertOk();
        expect($response->json('data'))->toHaveCount(1);
    });

    it('creates a mention', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();
        [$otherWorkspace, $otherAgent] = createWorkspaceWithAgent();

        $workspace->agents()->attach($otherAgent->id);

        $response = $this->postJson("/api/v1/workspaces/{$workspace->id}/mentions", [
            'target_agent_id' => $otherAgent->id,
            'message' => 'Can you help with this?',
        ], withAgent($agent));

        $response->assertCreated();
        expect($response->json('data.message'))->toBe('Can you help with this?');
        expect($response->json('data.status'))->toBe('pending');
    });

    it('responds to a mention', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();
        [$otherWorkspace, $otherAgent] = createWorkspaceWithAgent();

        $workspace->agents()->attach($otherAgent->id);

        $mention = CollaborationMention::create([
            'workspace_id' => $workspace->id,
            'agent_id' => $agent->id,
            'target_agent_id' => $otherAgent->id,
            'message' => 'Can you help with this?',
        ]);

        $response = $this->postJson("/api/v1/workspaces/{$workspace->id}/mentions/{$mention->id}/respond", [
            'response' => 'accepted',
            'response_text' => 'Sure, I can help!',
        ], withAgent($otherAgent));

        $response->assertOk();
        expect($response->json('data.status'))->toBe('accepted');
        expect($response->json('data.response'))->toBe('Sure, I can help!');
    });
});

// ===========================================================================
// Phase 4: Shared Tasks
// ===========================================================================

describe('Shared Tasks', function () {
    it('lists workspace tasks', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $response = $this->getJson("/api/v1/workspaces/{$workspace->id}/tasks", withAgent($agent));

        $response->assertOk();
        expect($response->json('data'))->toBeArray();
    });

    it('creates a task', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $response = $this->postJson("/api/v1/workspaces/{$workspace->id}/tasks", [
            'title' => 'Implement feature X',
            'description' => 'Full details here',
            'priority' => 'high',
        ], withAgent($agent));

        $response->assertCreated();
        expect($response->json('data.title'))->toBe('Implement feature X');
        expect($response->json('data.status'))->toBe('pending');
        expect($response->json('data.priority'))->toBe('high');
    });

    it('shows a task', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $task = WorkspaceTask::create([
            'workspace_id' => $workspace->id,
            'created_by_agent_id' => $agent->id,
            'title' => 'Test task',
            'status' => 'pending',
            'priority' => 'medium',
        ]);

        $response = $this->getJson("/api/v1/workspaces/{$workspace->id}/tasks/{$task->id}", withAgent($agent));

        $response->assertOk();
        expect($response->json('data.title'))->toBe('Test task');
    });

    it('updates a task', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $task = WorkspaceTask::create([
            'workspace_id' => $workspace->id,
            'created_by_agent_id' => $agent->id,
            'title' => 'Test task',
            'status' => 'pending',
            'priority' => 'medium',
        ]);

        $response = $this->patchJson("/api/v1/workspaces/{$workspace->id}/tasks/{$task->id}", [
            'title' => 'Updated task title',
            'priority' => 'high',
        ], withAgent($agent));

        $response->assertOk();
        expect($response->json('data.title'))->toBe('Updated task title');
        expect($response->json('data.priority'))->toBe('high');
    });

    it('assigns a task', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();
        [$otherWorkspace, $otherAgent] = createWorkspaceWithAgent();

        $workspace->agents()->attach($otherAgent->id);

        $task = WorkspaceTask::create([
            'workspace_id' => $workspace->id,
            'created_by_agent_id' => $agent->id,
            'title' => 'Test task',
            'status' => 'pending',
            'priority' => 'medium',
        ]);

        $response = $this->postJson("/api/v1/workspaces/{$workspace->id}/tasks/{$task->id}/assign", [
            'agent_id' => $otherAgent->id,
        ], withAgent($agent));

        $response->assertOk();
        expect($response->json('data.assigned_agent_id'))->toBe($otherAgent->id);
    });

    it('updates task status', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $task = WorkspaceTask::create([
            'workspace_id' => $workspace->id,
            'created_by_agent_id' => $agent->id,
            'title' => 'Test task',
            'status' => 'pending',
            'priority' => 'medium',
        ]);

        $response = $this->postJson("/api/v1/workspaces/{$workspace->id}/tasks/{$task->id}/status", [
            'status' => 'in_progress',
        ], withAgent($agent));

        $response->assertOk();
        expect($response->json('data.status'))->toBe('in_progress');
    });

    it('deletes a task', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $task = WorkspaceTask::create([
            'workspace_id' => $workspace->id,
            'created_by_agent_id' => $agent->id,
            'title' => 'Test task',
            'status' => 'pending',
            'priority' => 'medium',
        ]);

        $response = $this->deleteJson("/api/v1/workspaces/{$workspace->id}/tasks/{$task->id}", [], withAgent($agent));

        $response->assertOk();
        $this->assertDatabaseMissing('workspace_tasks', ['id' => $task->id]);
    });

    it('filters tasks by status', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        WorkspaceTask::create([
            'workspace_id' => $workspace->id,
            'created_by_agent_id' => $agent->id,
            'title' => 'Pending task',
            'status' => 'pending',
            'priority' => 'medium',
        ]);
        WorkspaceTask::create([
            'workspace_id' => $workspace->id,
            'created_by_agent_id' => $agent->id,
            'title' => 'In progress task',
            'status' => 'in_progress',
            'priority' => 'medium',
        ]);

        $response = $this->getJson("/api/v1/workspaces/{$workspace->id}/tasks?status=pending", withAgent($agent));

        $response->assertOk();
        expect($response->json('data'))->toHaveCount(1);
        expect($response->json('data.0.title'))->toBe('Pending task');
    });
});

// ===========================================================================
// Phase 2: Workspace Events (Memory Lifecycle)
// ===========================================================================

describe('Workspace Events on Memory Lifecycle', function () {
    it('dispatches memory.created event when storing workspace memory', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'A shared memory',
            'visibility' => 'workspace',
            'workspace_id' => $workspace->id,
        ], withAgent($agent));

        $response->assertCreated();

        $this->assertDatabaseHas('workspace_events', [
            'workspace_id' => $workspace->id,
            'event_type' => WorkspaceEvent::TYPE_MEMORY_CREATED,
            'actor_agent_id' => $agent->id,
        ]);
    });

    it('dispatches memory.updated event when updating workspace memory', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $memory = Memory::factory()->create([
            'agent_id' => $agent->id,
            'workspace_id' => $workspace->id,
            'visibility' => 'workspace',
            'value' => 'Original value',
        ]);

        $response = $this->patchJson("/api/v1/memories/{$memory->key}", [
            'value' => 'Updated value',
        ], withAgent($agent));

        $response->assertOk();

        $this->assertDatabaseHas('workspace_events', [
            'workspace_id' => $workspace->id,
            'event_type' => WorkspaceEvent::TYPE_MEMORY_UPDATED,
            'actor_agent_id' => $agent->id,
        ]);
    });

    it('dispatches memory.deleted event when deleting workspace memory', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $memory = Memory::factory()->create([
            'agent_id' => $agent->id,
            'workspace_id' => $workspace->id,
            'visibility' => 'workspace',
        ]);

        $response = $this->deleteJson("/api/v1/memories/{$memory->key}", [], withAgent($agent));

        $response->assertOk();

        $this->assertDatabaseHas('workspace_events', [
            'workspace_id' => $workspace->id,
            'event_type' => WorkspaceEvent::TYPE_MEMORY_DELETED,
            'actor_agent_id' => $agent->id,
        ]);
    });

    it('does not dispatch workspace events for non-workspace memories', function () {
        [$workspace, $agent] = createWorkspaceWithAgent();

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'A private memory',
            'visibility' => 'private',
        ], withAgent($agent));

        $response->assertCreated();

        $this->assertDatabaseMissing('workspace_events', [
            'event_type' => WorkspaceEvent::TYPE_MEMORY_CREATED,
        ]);
    });
});
