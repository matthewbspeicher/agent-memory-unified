<?php

use App\Models\InviteCode;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Mail;

uses(RefreshDatabase::class);

beforeEach(function () {
    Mail::fake();
});

describe('POST /login — invite-gated registration', function () {

    it('creates a new user with a valid invite code', function () {
        [$invite, $plainCode] = InviteCode::generate(label: 'test');

        $response = $this->postJson('/login', [
            'name' => 'New User',
            'email' => 'newuser@example.com',
            'invite_code' => $plainCode,
        ]);

        $response->assertOk()
            ->assertJsonFragment(['message' => 'Check your email for the magic link.']);

        $this->assertDatabaseHas('users', ['email' => 'newuser@example.com']);

        $invite->refresh();
        expect($invite->times_used)->toBe(1);
        expect($invite->used_by_id)->not->toBeNull();
    });

    it('rejects an expired invite code with 422', function () {
        [$invite, $plainCode] = InviteCode::generate(
            label: 'expired',
            expiresAt: now()->subDay(),
        );

        $response = $this->postJson('/login', [
            'name' => 'Should Fail',
            'email' => 'expired@example.com',
            'invite_code' => $plainCode,
        ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['invite_code']);

        $this->assertDatabaseMissing('users', ['email' => 'expired@example.com']);
    });

    it('rejects an exhausted invite code with 422', function () {
        [$invite, $plainCode] = InviteCode::generate(label: 'used-up', maxUses: 1);
        $invite->update(['times_used' => 1]);

        $response = $this->postJson('/login', [
            'name' => 'Should Fail',
            'email' => 'exhausted@example.com',
            'invite_code' => $plainCode,
        ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['invite_code']);

        $this->assertDatabaseMissing('users', ['email' => 'exhausted@example.com']);
    });

    it('rejects a new user without an invite code with 422', function () {
        $response = $this->postJson('/login', [
            'name' => 'No Code',
            'email' => 'nocode@example.com',
        ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['invite_code']);

        $this->assertDatabaseMissing('users', ['email' => 'nocode@example.com']);
    });

    it('allows an existing user to log in without an invite code', function () {
        User::factory()->create(['email' => 'existing@example.com']);

        $response = $this->postJson('/login', [
            'name' => 'Existing User',
            'email' => 'existing@example.com',
        ]);

        $response->assertOk()
            ->assertJsonFragment(['message' => 'Check your email for the magic link.']);
    });
});
