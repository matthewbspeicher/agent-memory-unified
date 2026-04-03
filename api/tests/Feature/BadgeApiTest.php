<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

it('returns a memories count badge', function () {
    $owner = User::factory()->create(['api_token' => 'owner_token']);
    $agent = Agent::factory()->create(['owner_id' => $owner->id]);

    Memory::factory(3)->create(['agent_id' => $agent->id]);

    $response = $this->get('/api/v1/badges/agent/'.$agent->id.'/memories');

    $response->assertOk();
    $response->assertHeader('Content-Type', 'image/svg+xml');

    $content = $response->getContent();
    expect($content)->toContain('<svg');
    expect($content)->toContain('memories');
    expect($content)->toContain('3');
});

it('returns a status badge', function () {
    $owner = User::factory()->create(['api_token' => 'owner_token']);
    $agent = Agent::factory()->create([
        'owner_id' => $owner->id,
        'last_seen_at' => now(),
    ]);

    $response = $this->get('/api/v1/badges/agent/'.$agent->id.'/status');

    $response->assertOk();
    $response->assertHeader('Content-Type', 'image/svg+xml');

    $content = $response->getContent();
    expect($content)->toContain('<svg');
    expect($content)->toContain('status');
    expect($content)->toContain('active');
});

it('returns 404 for missing agent', function () {
    $response = $this->get('/api/v1/badges/agent/00000000-0000-0000-0000-000000000000/memories');
    $response->assertNotFound();
});
