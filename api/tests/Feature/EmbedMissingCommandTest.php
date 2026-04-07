<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Services\EmbeddingService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->owner = makeOwner(['_plaintext_override' => 'embed_test_owner']);
    $this->agent = makeAgent($this->owner, ['_token' => 'amc_embed_test']);
});

it('embeds memories that are missing embeddings', function () {
    $this->mock(\App\Contracts\EmbeddingServiceInterface::class, function ($mock) {
        $mock->shouldReceive('embedBatch')
            ->once()
            ->andReturn([array_fill(0, 1536, 0.5)]);
    });

    Memory::factory()->create([
        'agent_id' => $this->agent->id,
        'value' => 'needs embedding',
        'embedding' => null,
    ]);

    $this->artisan('memories:embed-missing')
        ->assertExitCode(0);

    $memory = Memory::first();
    expect($memory->embedding)->not->toBeNull();
});

it('skips memories that already have embeddings', function () {
    $this->mock(\App\Contracts\EmbeddingServiceInterface::class, function ($mock) {
        $mock->shouldNotReceive('embedBatch');
    });

    Memory::factory()->create([
        'agent_id' => $this->agent->id,
        'value' => 'already embedded',
        // factory default already sets a valid embedding string; rely on it
    ]);

    $this->artisan('memories:embed-missing')
        ->assertExitCode(0);
});
