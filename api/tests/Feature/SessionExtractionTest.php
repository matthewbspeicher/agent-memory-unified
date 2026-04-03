<?php

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
        $mock->shouldReceive('generateSummary')->andReturn(null);
        $mock->shouldReceive('extractMemories')->andReturn([
            [
                'value' => 'User prefers dark mode for all editors',
                'type' => 'preference',
                'key' => 'pref-dark-mode',
                'importance' => 7,
            ],
            [
                'value' => 'Project uses Laravel 12 with PostgreSQL',
                'type' => 'fact',
                'key' => 'stack-laravel-pg',
                'importance' => 8,
            ],
        ]);
    });
});

// ---------------------------------------------------------------------------
// Session Extraction
// ---------------------------------------------------------------------------

describe('POST /v1/sessions/extract', function () {

    it('extracts memories from a transcript', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/sessions/extract', [
            'transcript' => "User: I really prefer dark mode in my editors.\nAssistant: I'll remember that preference.\nUser: We're using Laravel 12 with PostgreSQL.\nAssistant: Got it, noted for future reference.",
        ], withAgent($agent));

        $response->assertCreated()
            ->assertJsonCount(2, 'data')
            ->assertJsonPath('meta.extracted_count', 2)
            ->assertJsonPath('meta.stored_count', 2);

        // Verify the memories were actually created
        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'key' => 'pref-dark-mode',
        ]);
        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'key' => 'stack-laravel-pg',
        ]);
    });

    it('assigns default category to extracted memories', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/sessions/extract', [
            'transcript' => "User: Remember this important thing.\nAssistant: Noted.",
        ], withAgent($agent));

        $response->assertCreated();

        // Default category is 'session-extraction'
        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'category' => 'session-extraction',
        ]);
    });

    it('accepts custom category for extracted memories', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/sessions/extract', [
            'transcript' => "User: Some important conversation content here.\nAssistant: Understood.",
            'category' => 'meeting-notes',
        ], withAgent($agent));

        $response->assertCreated();

        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'category' => 'meeting-notes',
        ]);
    });

    it('rejects missing transcript', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/sessions/extract', [], withAgent($agent))
            ->assertUnprocessable();
    });

    it('rejects transcript that is too short', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/sessions/extract', [
            'transcript' => 'Too short',
        ], withAgent($agent))
            ->assertUnprocessable();
    });

    it('returns empty data when nothing worth extracting', function () {
        $agent = makeAgent(makeOwner());

        $this->mock(SummarizationService::class, function ($mock) {
            $mock->shouldReceive('generateSummary')->andReturn(null);
            $mock->shouldReceive('extractMemories')->andReturn([]);
        });

        $response = $this->postJson('/api/v1/sessions/extract', [
            'transcript' => "User: Hello, how are you?\nAssistant: I'm doing well, thank you!",
        ], withAgent($agent));

        $response->assertOk()
            ->assertJsonPath('meta.extracted_count', 0);
    });
});
