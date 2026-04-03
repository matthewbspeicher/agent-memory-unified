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

describe('memories:prune command', function () {
    it('deletes expired memories and keeps non-expired ones', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'expired',
            'expires_at' => now()->subDay(),
        ]);

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'active',
            'expires_at' => now()->addDay(),
        ]);

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'no-expiry',
            'expires_at' => null,
        ]);

        $this->artisan('memories:prune')->assertExitCode(0);

        $this->assertDatabaseMissing('memories', ['key' => 'expired']);
        $this->assertDatabaseHas('memories', ['key' => 'active']);
        $this->assertDatabaseHas('memories', ['key' => 'no-expiry']);
    });
});
