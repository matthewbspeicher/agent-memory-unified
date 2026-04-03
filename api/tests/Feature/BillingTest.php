<?php

use App\Listeners\SyncAgentQuotas;
use App\Models\User;
use App\Models\Workspace;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Str;
use Laravel\Cashier\Checkout;
use Laravel\Cashier\Events\WebhookReceived;
use Laravel\Cashier\SubscriptionBuilder;

uses(RefreshDatabase::class);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeProUser(array $overrides = []): User
{
    $user = makeOwner(array_merge([
        'stripe_id' => 'cus_test_'.Str::random(10),
    ], $overrides));

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

    return $user->fresh();
}

// ---------------------------------------------------------------------------
// Plan Helper Tests
// ---------------------------------------------------------------------------

describe('plan helpers', function () {
    it('returns false for isPro when user has no subscription', function () {
        $user = makeOwner();
        expect($user->isPro())->toBeFalse();
    });

    it('returns true for isPro when user has active subscription', function () {
        $user = makeProUser();
        expect($user->isPro())->toBeTrue();
    });

    it('returns 5 max agents for free user', function () {
        $user = makeOwner();
        expect($user->maxAgents())->toBe(5);
    });

    it('returns PHP_INT_MAX max agents for pro user', function () {
        $user = makeProUser();
        expect($user->maxAgents())->toBe(PHP_INT_MAX);
    });

    it('returns unlimited max agents for allowlisted email', function () {
        config(['app.unlimited_agent_emails' => ['vip@example.com']]);

        $user = makeOwner(['email' => 'vip@example.com']);

        expect($user->maxAgents())->toBe(PHP_INT_MAX);
    });

    it('returns 1000 max memories per agent for free user', function () {
        $user = makeOwner();
        expect($user->maxMemoriesPerAgent())->toBe(1000);
    });

    it('returns 10000 max memories per agent for pro user', function () {
        $user = makeProUser();
        expect($user->maxMemoriesPerAgent())->toBe(10000);
    });

    it('returns false for canCreateWorkspace for free user', function () {
        $user = makeOwner();
        expect($user->canCreateWorkspace())->toBeFalse();
    });

    it('returns true for canCreateWorkspace for pro user', function () {
        $user = makeProUser();
        expect($user->canCreateWorkspace())->toBeTrue();
    });

    it('returns true for isDowngraded when free user has more than the default agent limit', function () {
        $user = makeOwner();
        for ($i = 0; $i < 6; $i++) {
            makeAgent($user, ['api_token' => 'amc_'.Str::random(40)]);
        }
        expect($user->isDowngraded())->toBeTrue();
    });

    it('returns true for isDowngraded when not pro but owns workspaces', function () {
        $user = makeOwner();
        Workspace::factory()->create(['owner_id' => $user->id]);
        expect($user->isDowngraded())->toBeTrue();
    });

    it('returns false for isDowngraded for pro user with many agents', function () {
        $user = makeProUser();
        for ($i = 0; $i < 6; $i++) {
            makeAgent($user, ['api_token' => 'amc_'.Str::random(40)]);
        }
        expect($user->isDowngraded())->toBeFalse();
    });

    it('returns false for isDowngraded for allowlisted email with many agents', function () {
        config(['app.unlimited_agent_emails' => ['vip@example.com']]);

        $user = makeOwner(['email' => 'vip@example.com']);
        for ($i = 0; $i < 6; $i++) {
            makeAgent($user, ['api_token' => 'amc_'.Str::random(40)]);
        }

        expect($user->isDowngraded())->toBeFalse();
    });

    it('returns false for isDowngraded for free user within limits and no workspaces', function () {
        $user = makeOwner();
        makeAgent($user);
        expect($user->isDowngraded())->toBeFalse();
    });
});

// ---------------------------------------------------------------------------
// Agent Cap Enforcement
// ---------------------------------------------------------------------------

describe('agent creation cap', function () {
    it('allows free user to register 5 agents via API', function () {
        $owner = makeOwner();
        for ($i = 0; $i < 5; $i++) {
            $response = $this->postJson('/api/v1/agents/register', [
                'name' => "Agent $i",
                'owner_token' => $owner->api_token,
            ]);
            $response->assertStatus(201);
        }
    });

    it('blocks free user from registering 6th agent via API', function () {
        $owner = makeOwner();
        for ($i = 0; $i < 5; $i++) {
            makeAgent($owner, ['api_token' => 'amc_'.Str::random(40)]);
        }

        $response = $this->postJson('/api/v1/agents/register', [
            'name' => 'Agent 6',
            'owner_token' => $owner->api_token,
        ]);
        $response->assertStatus(403);
        $response->assertJsonFragment(['error' => 'Agent limit reached. Upgrade to Pro for unlimited agents.']);
    });

    it('allows allowlisted free user to register unlimited agents via API', function () {
        config(['app.unlimited_agent_emails' => ['vip@example.com']]);

        $owner = makeOwner(['email' => 'vip@example.com']);

        for ($i = 0; $i < 6; $i++) {
            $response = $this->postJson('/api/v1/agents/register', [
                'name' => "Agent $i",
                'owner_token' => $owner->api_token,
            ]);

            $response->assertStatus(201);
        }
    });

    it('allows pro user to register unlimited agents via API', function () {
        $owner = makeProUser();
        for ($i = 0; $i < 6; $i++) {
            $response = $this->postJson('/api/v1/agents/register', [
                'name' => "Agent $i",
                'owner_token' => $owner->api_token,
            ]);
            $response->assertStatus(201);
        }
    });

    it('blocks free user from registering 6th agent via dashboard', function () {
        $owner = makeOwner();
        for ($i = 0; $i < 5; $i++) {
            makeAgent($owner, ['api_token' => 'amc_'.Str::random(40)]);
        }

        $response = $this->actingAs($owner)->post('/dashboard/agents', [
            'name' => 'Agent 6',
        ]);
        $response->assertSessionHasErrors('name');
    });
});

// ---------------------------------------------------------------------------
// Workspace Gate
// ---------------------------------------------------------------------------

describe('workspace creation gate', function () {
    it('blocks free user from creating workspaces', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner);

        $response = $this->postJson('/api/v1/workspaces', [
            'name' => 'Private Workspace',
        ], withAgent($agent));

        $response->assertStatus(403);
        $response->assertJsonFragment(['error' => 'Private workspaces require a Pro subscription.']);
    });

    it('allows pro user to create workspaces', function () {
        $owner = makeProUser();
        $agent = makeAgent($owner);

        $response = $this->postJson('/api/v1/workspaces', [
            'name' => 'Private Workspace',
        ], withAgent($agent));

        $response->assertStatus(201);
    });
});

// ---------------------------------------------------------------------------
// Soft Lock on Downgrade
// ---------------------------------------------------------------------------

describe('soft lock on downgrade', function () {

    beforeEach(function () {
        // Mock embeddings for memory store tests
        $mock = Mockery::mock(EmbeddingService::class);
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
        app()->instance(EmbeddingService::class, $mock);
    });

    it('blocks write on 6th agent when downgraded', function () {
        $owner = makeOwner();
        $agents = [];
        for ($i = 0; $i < 6; $i++) {
            $agents[] = makeAgent($owner);
        }

        // 6th agent (by created_at) should be read-only
        $response = $this->postJson('/api/v1/memories', [
            'value' => 'test memory',
        ], withAgent($agents[5]));

        $response->assertStatus(403);
        $response->assertJsonFragment(['error' => 'This agent is in read-only mode. Upgrade to Pro to restore write access.']);
    });

    it('allows read on 6th agent when downgraded', function () {
        $owner = makeOwner();
        $agents = [];
        for ($i = 0; $i < 6; $i++) {
            $agents[] = makeAgent($owner);
        }

        $response = $this->getJson('/api/v1/memories', withAgent($agents[5]));
        $response->assertOk();
    });

    it('allows write on first 5 agents when downgraded', function () {
        $owner = makeOwner();
        $agents = [];
        for ($i = 0; $i < 6; $i++) {
            $agents[] = makeAgent($owner);
        }

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'test memory',
        ], withAgent($agents[0]));

        $response->assertStatus(201);
    });

    it('blocks workspace memory writes when downgraded', function () {
        $owner = makeOwner();
        $agent = makeAgent($owner);
        $workspace = Workspace::factory()->create(['owner_id' => $owner->id]);
        $agent->workspaces()->attach($workspace->id);

        // Owner is downgraded because they own a workspace but have no Pro sub
        $response = $this->postJson('/api/v1/memories', [
            'value' => 'workspace memory',
            'workspace_id' => $workspace->id,
        ], withAgent($agent));

        $response->assertStatus(403);
        $response->assertJsonFragment(['error' => 'Workspace memories are read-only. Upgrade to Pro to restore write access.']);
    });
});

// ---------------------------------------------------------------------------
// Billing Routes
// ---------------------------------------------------------------------------

describe('billing routes', function () {
    it('redirects unauthenticated user from checkout to login', function () {
        $this->get('/billing/checkout')
            ->assertRedirect('/login');
    });

    it('redirects unauthenticated user from portal to login', function () {
        $this->get('/billing/portal')
            ->assertRedirect('/login');
    });

    it('renders pricing page for guests', function () {
        $this->get('/pricing')
            ->assertOk();
    });

    it('renders pricing page for authenticated users', function () {
        $user = makeOwner();
        $this->actingAs($user)->get('/pricing')
            ->assertOk();
    });

    it('renders success page for authenticated users', function () {
        $user = makeOwner();
        $this->actingAs($user)->get('/billing/success')
            ->assertRedirect('/dashboard');
    });

    it('creates checkout session for authenticated user', function () {
        $user = makeOwner(['stripe_id' => 'cus_checkout_test']);

        $checkoutMock = Mockery::mock(Checkout::class);
        $checkoutMock->shouldReceive('toResponse')->andReturn(
            redirect('https://checkout.stripe.com/test')
        );

        $builderMock = Mockery::mock(SubscriptionBuilder::class);
        $builderMock->shouldReceive('checkout')->andReturn($checkoutMock);

        $userMock = Mockery::mock($user)->makePartial();
        $userMock->shouldReceive('newSubscription')->andReturn($builderMock);

        $this->actingAs($userMock);
        $response = $this->get('/billing/checkout');
        $response->assertRedirect();
    });

    it('redirects pro user to billing portal', function () {
        $user = makeProUser();

        $userMock = Mockery::mock($user)->makePartial();
        $userMock->shouldReceive('redirectToBillingPortal')
            ->andReturn(redirect('https://billing.stripe.com/portal/test'));

        $this->actingAs($userMock);
        $response = $this->get('/billing/portal');
        $response->assertRedirect();
    });
});

// ---------------------------------------------------------------------------
// Quota Sync
// ---------------------------------------------------------------------------

describe('quota sync', function () {
    it('sets max_memories to 10000 when user subscribes', function () {
        $user = makeOwner(['stripe_id' => 'cus_sync_test']);
        $agent = makeAgent($user);

        expect($agent->fresh()->max_memories)->toBe(1000);

        // Simulate subscription created webhook
        $event = new WebhookReceived([
            'type' => 'customer.subscription.created',
            'data' => ['object' => ['customer' => 'cus_sync_test']],
        ]);

        // Before creating subscription, make user Pro
        $subscription = $user->subscriptions()->create([
            'type' => 'default',
            'stripe_id' => 'sub_sync_test',
            'stripe_status' => 'active',
            'stripe_price' => 'price_test',
            'quantity' => 1,
        ]);
        $subscription->items()->create([
            'stripe_id' => 'si_sync_test',
            'stripe_product' => 'prod_test',
            'stripe_price' => 'price_test',
            'quantity' => 1,
        ]);

        $listener = new SyncAgentQuotas;
        $listener->handle($event);

        expect($agent->fresh()->max_memories)->toBe(10000);
    });

    it('sets max_memories to 1000 when subscription is deleted', function () {
        $user = makeProUser(['stripe_id' => 'cus_downgrade_test']);
        $agent = makeAgent($user, ['max_memories' => 10000]);

        // Delete the subscription to simulate downgrade
        $user->subscriptions()->delete();

        $event = new WebhookReceived([
            'type' => 'customer.subscription.deleted',
            'data' => ['object' => ['customer' => 'cus_downgrade_test']],
        ]);

        $listener = new SyncAgentQuotas;
        $listener->handle($event);

        expect($agent->fresh()->max_memories)->toBe(1000);
    });
});

describe('dashboard billing props', function () {
    it('passes billing props to dashboard for free user', function () {
        $user = makeOwner();
        makeAgent($user);

        $response = $this->actingAs($user)->get('/dashboard');
        $response->assertOk();
        $response->assertInertia(fn ($page) => $page
            ->component('Dashboard')
            ->has('isPro')
            ->has('isDowngraded')
            ->has('isOnGracePeriod')
            ->has('hasPaymentFailure')
            ->has('currentPlan')
            ->has('agentCount')
            ->has('maxAgents')
            ->has('avgMemoriesPerAgent')
            ->has('maxMemoriesPerAgent')
            ->where('isPro', false)
            ->where('currentPlan', 'free')
        );
    });

    it('passes pro billing props to dashboard', function () {
        $user = makeProUser();

        $response = $this->actingAs($user)->get('/dashboard');
        $response->assertOk();
        $response->assertInertia(fn ($page) => $page
            ->component('Dashboard')
            ->where('isPro', true)
            ->where('currentPlan', 'pro')
            ->where('maxAgents', 'unlimited')
        );
    });

    it('passes unlimited billing props to dashboard for allowlisted user', function () {
        config(['app.unlimited_agent_emails' => ['vip@example.com']]);

        $user = makeOwner(['email' => 'vip@example.com']);

        $response = $this->actingAs($user)->get('/dashboard');
        $response->assertOk();
        $response->assertInertia(fn ($page) => $page
            ->component('Dashboard')
            ->where('isPro', false)
            ->where('currentPlan', 'unlimited')
            ->where('maxAgents', 'unlimited')
        );
    });
});
