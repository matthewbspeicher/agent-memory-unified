<?php

use App\Models\Memory;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
    });
});

describe('GET /v1/commons/poll', function () {
    it('returns public memories', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'visibility' => 'public',
            'value' => 'public memory',
        ]);

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'visibility' => 'private',
            'value' => 'private memory',
        ]);

        $response = $this->getJson('/api/v1/commons/poll');

        $response->assertOk()
            ->assertJsonStructure(['memories', 'total_memories', 'server_time']);

        $values = collect($response->json('memories'))->pluck('value');
        expect($values)->toContain('public memory')
            ->not->toContain('private memory');
    });

    it('filters by since parameter', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'visibility' => 'public',
            'value' => 'old memory',
            'created_at' => now()->subHour(),
        ]);

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'visibility' => 'public',
            'value' => 'new memory',
            'created_at' => now(),
        ]);

        $since = urlencode(now()->subMinutes(30)->toIso8601String());
        $response = $this->getJson("/api/v1/commons/poll?since=$since");

        $response->assertOk();
        $values = collect($response->json('memories'))->pluck('value');
        expect($values)->toContain('new memory')
            ->not->toContain('old memory');
    });

    it('returns without authentication', function () {
        $this->getJson('/api/v1/commons/poll')->assertOk();
    });
});
