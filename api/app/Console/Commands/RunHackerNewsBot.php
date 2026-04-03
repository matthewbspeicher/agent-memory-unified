<?php

namespace App\Console\Commands;

use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class RunHackerNewsBot extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'bot:hackernews';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Fetches the top Hacker News story and saves it to the commons';

    /**
     * Execute the console command.
     */
    public function handle()
    {
        $bot = Agent::where('name', '@HackerNewsBot')->first();

        if (! $bot) {
            $this->error('@HackerNewsBot agent not found. Did you run the Seeder?');

            return Command::FAILURE;
        }

        $this->info('Fetching top HN stories...');

        $response = Http::get('https://hacker-news.firebaseio.com/v0/topstories.json');

        if ($response->failed()) {
            Log::error('HackerNewsBot: Failed to fetch top stories.');
            $this->error('Failed to fetch from HN API');

            return Command::FAILURE;
        }

        $topStoryIds = $response->json();

        if (empty($topStoryIds)) {
            Log::error('HackerNewsBot: Received empty array from topstories.');
            $this->error('Received empty array from HN API.');

            return Command::FAILURE;
        }

        // Just get the top story
        $storyId = collect($topStoryIds)->first();

        $storyResponse = Http::get("https://hacker-news.firebaseio.com/v0/item/{$storyId}.json");

        if ($storyResponse->failed()) {
            Log::error("HackerNewsBot: Failed to fetch story details for ID: {$storyId}");
            $this->error("Failed to fetch story details for ID: {$storyId}");

            return Command::FAILURE;
        }

        $story = $storyResponse->json();

        // Prevent storing duplicates near the same time
        $existing = Memory::where('agent_id', $bot->id)
            ->where('key', 'like', "%hn_top_story_{$storyId}%")
            ->exists();

        if ($existing) {
            $this->info("Story {$storyId} already stored recently. Skipping.");

            return Command::SUCCESS;
        }

        $content = 'Top HN Story: '.($story['title'] ?? 'Unknown Title');
        if (isset($story['url'])) {
            $content .= "\nURL: {$story['url']}";
        }

        Memory::create([
            'agent_id' => $bot->id,
            'key' => "hn_top_story_{$storyId}",
            'value' => $content,
            'type' => 'article',
            'visibility' => 'public',
        ]);

        $this->info("Successfully stored HN Story {$storyId}.");

        return Command::SUCCESS;
    }
}
