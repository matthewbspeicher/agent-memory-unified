<?php

use App\Models\Agent;
use App\Models\Memory;
use Database\Seeders\LaunchBotsSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;

uses(RefreshDatabase::class);

test('hacker news bot runs and stories memory', function () {
    $this->seed(LaunchBotsSeeder::class);

    // Mock the HN API calls
    Http::fake([
        'hacker-news.firebaseio.com/v0/topstories.json' => Http::response([12345], 200),
        'hacker-news.firebaseio.com/v0/item/12345.json' => Http::response([
            'id' => 12345,
            'title' => 'Show HN: A New Test Framework',
            'url' => 'https://example.com/test-framework',
        ], 200),
    ]);

    $this->artisan('bot:hackernews')
        ->assertSuccessful()
        ->expectsOutputToContain('Successfully stored HN Story 12345');

    $bot = Agent::where('name', '@HackerNewsBot')->first();

    $this->assertDatabaseHas('memories', [
        'agent_id' => $bot->id,
        'key' => 'hn_top_story_12345',
        'type' => 'article',
        'visibility' => 'public',
    ]);
});

test('prompt engineer bot runs and stores prompt memory', function () {
    $this->seed(LaunchBotsSeeder::class);

    $this->artisan('bot:promptengineer')
        ->assertSuccessful()
        ->expectsOutputToContain('Successfully posted prompt tip');

    $bot = Agent::where('name', '@PromptEngineer')->first();

    $this->assertEquals(1, Memory::where('agent_id', $bot->id)->where('type', 'prompt')->count());
});

test('system observer bot runs and stores telemetry memory', function () {
    $this->seed(LaunchBotsSeeder::class);

    $this->artisan('bot:systemobserver')
        ->assertSuccessful()
        ->expectsOutputToContain('Successfully posted telemetry overview');

    $bot = Agent::where('name', '@SystemObserver')->first();

    $this->assertEquals(1, Memory::where('agent_id', $bot->id)->where('type', 'system')->count());
});
