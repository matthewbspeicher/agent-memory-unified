<?php

use App\Mail\MagicLinkMail;
use App\Models\Agent;
use App\Models\User;
use Illuminate\Support\Facades\Mail;

beforeEach(function () {
    Mail::fake();
});

test('login page renders', function () {
    $this->get('/login')->assertOk();
});

test('sending magic link creates user and sends email', function () {
    $this->withSession(['_token' => 'test-token'])
        ->post('/login', [
            '_token' => 'test-token',
            'name' => 'Test User',
            'email' => 'test@example.com',
        ])->assertRedirect('/auth/check-email');

    $this->assertDatabaseHas('users', ['email' => 'test@example.com']);

    Mail::assertSent(MagicLinkMail::class, function ($mail) {
        return $mail->hasTo('test@example.com');
    });
});

test('sending magic link for existing user does not duplicate', function () {
    User::factory()->create(['email' => 'existing@example.com']);

    $this->withSession(['_token' => 'test-token'])
        ->post('/login', [
            '_token' => 'test-token',
            'name' => 'Existing',
            'email' => 'existing@example.com',
        ])->assertRedirect('/auth/check-email');

    expect(User::where('email', 'existing@example.com')->count())->toBe(1);
});

test('valid magic link logs user in', function () {
    $user = User::factory()->create();
    $token = $user->generateMagicLink();

    $this->get("/auth/verify/{$token}")
        ->assertRedirect('/dashboard');

    $this->assertAuthenticatedAs($user);
});

test('expired magic link is rejected', function () {
    $user = User::factory()->create();
    $token = $user->generateMagicLink();

    // Expire the token
    $user->update(['magic_link_expires_at' => now()->subMinute()]);

    $this->get("/auth/verify/{$token}")
        ->assertRedirect('/login');

    $this->assertGuest();
});

test('used magic link cannot be reused', function () {
    $user = User::factory()->create();
    $token = $user->generateMagicLink();

    // First use — works
    $this->get("/auth/verify/{$token}")
        ->assertRedirect('/dashboard');

    // Logout
    $this->withSession(['_token' => 'test-token'])
        ->post('/logout', ['_token' => 'test-token']);

    // Second use — fails
    $this->get("/auth/verify/{$token}")
        ->assertRedirect('/login');
});

test('invalid magic link is rejected', function () {
    $this->get('/auth/verify/totally-fake-token')
        ->assertRedirect('/login');

    $this->assertGuest();
});

test('dashboard requires authentication', function () {
    $this->get('/dashboard')
        ->assertRedirect('/login');
});

test('dashboard shows api token and agents', function () {
    $user = User::factory()->create(['api_token' => 'own_test_token_123']);
    Agent::factory()->create([
        'owner_id' => $user->id,
        'name' => 'TestBot',
    ]);

    $this->actingAs($user)
        ->get('/dashboard')
        ->assertOk()
        ->assertInertia(fn ($page) => $page
            ->component('Dashboard')
            ->where('apiToken', 'own_test_token_123')
            ->has('agents', 1)
        );
});

test('registering an agent from dashboard creates agent', function () {
    $user = User::factory()->create();

    $this->actingAs($user)
        ->withSession(['_token' => 'test-token'])
        ->post('/dashboard/agents', [
            '_token' => 'test-token',
            'name' => 'NewBot',
            'description' => 'A test bot',
        ])
        ->assertRedirect();

    $this->assertDatabaseHas('agents', [
        'owner_id' => $user->id,
        'name' => 'NewBot',
    ]);
});

test('login validates required fields', function () {
    $this->withSession(['_token' => 'test-token'])
        ->post('/login', ['_token' => 'test-token'])
        ->assertSessionHasErrors(['name', 'email']);
});

test('ensureApiToken generates token on login if missing', function () {
    $user = User::factory()->create(['api_token' => null]);
    $token = $user->generateMagicLink();

    $this->get("/auth/verify/{$token}")
        ->assertRedirect('/dashboard');

    $user->refresh();
    expect($user->api_token)->toStartWith('own_');
});
