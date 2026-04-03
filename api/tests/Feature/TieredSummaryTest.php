<?php

use App\Models\Memory;
use App\Services\EmbeddingService;
use App\Services\SummarizationService;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')
            ->andReturn(array_fill(0, 1536, 0.1));
    });

    $this->mock(SummarizationService::class, function ($mock) {
        $mock->shouldReceive('generateSummary')
            ->andReturn('A concise summary of the memory content.');
        $mock->shouldReceive('summarize')
            ->andReturn('Compacted summary.');
    });
});

// ---------------------------------------------------------------------------
// Tiered Summaries
// ---------------------------------------------------------------------------

describe('Tiered Memory Summaries', function () {

    it('auto-generates a summary when storing a long memory', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/memories', [
            'key' => 'long-memory',
            'value' => str_repeat('This is a detailed memory with lots of content. ', 10),
        ], withAgent($agent));

        $response->assertCreated()
            ->assertJsonPath('summary', 'A concise summary of the memory content.');
    });

    it('includes summary field in API responses', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories', [
            'key' => 'with-summary',
            'value' => str_repeat('A detailed explanation of a complex topic. ', 5),
        ], withAgent($agent))->assertCreated();

        $this->getJson('/api/v1/memories/with-summary', withAgent($agent))
            ->assertOk()
            ->assertJsonStructure(['summary']);
    });

    it('regenerates summary when value is updated', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories', [
            'key' => 'update-summary',
            'value' => str_repeat('Original content. ', 10),
        ], withAgent($agent))->assertCreated();

        $this->patchJson('/api/v1/memories/update-summary', [
            'value' => str_repeat('Completely new content that needs a new summary. ', 10),
        ], withAgent($agent))
            ->assertOk()
            ->assertJsonPath('summary', 'A concise summary of the memory content.');
    });

    it('returns summary in search results', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories', [
            'key' => 'searchable',
            'value' => str_repeat('Searchable content. ', 10),
        ], withAgent($agent))->assertCreated();

        $this->getJson('/api/v1/memories/search?q=searchable', withAgent($agent))
            ->assertOk()
            ->assertJsonPath('data.0.summary', 'A concise summary of the memory content.');
    });
});

// ---------------------------------------------------------------------------
// Detail Level
// ---------------------------------------------------------------------------

describe('Detail Level on Responses', function () {

    it('returns summary as value when detail=summary', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'detail-test',
            'value' => 'This is the full value of the memory.',
            'summary' => 'Short summary.',
        ]);

        $this->getJson('/api/v1/memories/detail-test?detail=summary', withAgent($agent))
            ->assertOk()
            ->assertJsonPath('value', 'Short summary.')
            ->assertJsonPath('has_full_content', true);
    });

    it('returns full value by default', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'detail-full',
            'value' => 'This is the full value.',
            'summary' => 'Short summary.',
        ]);

        $this->getJson('/api/v1/memories/detail-full', withAgent($agent))
            ->assertOk()
            ->assertJsonPath('value', 'This is the full value.')
            ->assertJsonPath('has_full_content', false);
    });

    it('works with list endpoint detail=summary', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'list-detail',
            'value' => 'Full value here.',
            'summary' => 'Listed summary.',
        ]);

        $this->getJson('/api/v1/memories?detail=summary', withAgent($agent))
            ->assertOk()
            ->assertJsonPath('data.0.value', 'Listed summary.')
            ->assertJsonPath('data.0.has_full_content', true);
    });
});
