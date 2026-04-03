<?php

use App\Events\MemoryCreated;
use App\Jobs\DispatchWebhook;
use App\Listeners\EvaluateSemanticWebhooks;
use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Models\WebhookSubscription;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Queue;

uses(RefreshDatabase::class);

it('triggers a webhook when a semantically similar public memory is created', function () {
    Queue::fake([DispatchWebhook::class]);

    $user = User::factory()->create();

    // Agent A creates a subscription
    $agentA = Agent::factory()->create(['owner_id' => $user->id]);

    // Give it an embedding that strongly matches index 0
    $subVector = array_fill(0, 1536, 0.0);
    $subVector[0] = 1.0;

    $sub = WebhookSubscription::create([
        'agent_id' => $agentA->id,
        'url' => 'https://example.com/webhook',
        'events' => ['memory.semantic_match'],
        'semantic_query' => 'I care about vector zero',
        'embedding' => '['.implode(',', $subVector).']',
        'is_active' => true,
        'secret' => 'fake_secret_key',
    ]);

    // Agent B creates a matching memory
    $agentB = Agent::factory()->create(['owner_id' => $user->id]);

    $memVector = array_fill(0, 1536, 0.0);
    $memVector[0] = 0.9; // High similarity to subscription

    $memory = Memory::create([
        'agent_id' => $agentB->id,
        'key' => 'matching-memory',
        'value' => 'This matches vector zero',
        'embedding' => '['.implode(',', $memVector).']',
        'visibility' => 'public',
    ]);

    // The listener is queued, so we just instantiate it and call handle() directly to test its logic
    $listener = new EvaluateSemanticWebhooks;
    $listener->handle(new MemoryCreated($memory));

    // The job should be dispatched for this subscription
    Queue::assertPushed(DispatchWebhook::class, function ($job) use ($sub) {
        return $job->subscription->id === $sub->id && $job->event === 'memory.semantic_match';
    });
});

it('does not trigger a webhook for low similarity memories', function () {
    Queue::fake([DispatchWebhook::class]);

    $user = User::factory()->create();

    $agentA = Agent::factory()->create(['owner_id' => $user->id]);

    $subVector = array_fill(0, 1536, 0.0);
    $subVector[0] = 1.0;

    $sub = WebhookSubscription::create([
        'agent_id' => $agentA->id,
        'url' => 'https://example.com/webhook',
        'events' => ['memory.semantic_match'],
        'semantic_query' => 'I care about vector zero',
        'embedding' => '['.implode(',', $subVector).']',
        'is_active' => true,
        'secret' => 'fake_secret_key',
    ]);

    $agentB = Agent::factory()->create(['owner_id' => $user->id]);

    // Completely orthogonal vector
    $memVector = array_fill(0, 1536, 0.0);
    $memVector[1] = 1.0;

    $memory = Memory::create([
        'agent_id' => $agentB->id,
        'key' => 'unrelated-memory',
        'value' => 'This does not match',
        'embedding' => '['.implode(',', $memVector).']',
        'visibility' => 'public',
    ]);

    // The listener is queued, so we just instantiate it and call handle() directly to test its logic
    $listener = new EvaluateSemanticWebhooks;
    $listener->handle(new MemoryCreated($memory));

    Queue::assertNotPushed(DispatchWebhook::class);
});
