<?php

use App\Models\Memory;
use App\Services\EmbeddingService;
use App\Services\SummarizationService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')->andReturn(array_fill(0, 1536, 0.1));
    });
});

describe('POST /v1/memories/compact error paths', function () {
    it('returns 422 when fewer than 2 matching memories', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'm1']);

        $this->mock(SummarizationService::class);

        $this->postJson('/api/v1/memories/compact', [
            'keys' => ['m1', 'nonexistent'],
            'summary_key' => 'summary',
        ], withAgent($agent))
            ->assertStatus(422)
            ->assertJsonFragment(['error' => 'Not enough valid memories found to compact.']);
    });

    it('returns 500 when summarization fails', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'm1', 'value' => 'Fact 1']);
        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'm2', 'value' => 'Fact 2']);

        $this->mock(SummarizationService::class, function ($mock) {
            $mock->shouldReceive('summarize')->once()->andThrow(new RuntimeException('API error'));
        });

        $this->postJson('/api/v1/memories/compact', [
            'keys' => ['m1', 'm2'],
            'summary_key' => 'summary',
        ], withAgent($agent))
            ->assertStatus(500)
            ->assertJsonFragment(['error' => 'Failed to generate summary. Please try again later.']);
    });
});
