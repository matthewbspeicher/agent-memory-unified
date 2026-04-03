<?php

namespace App\Console\Commands;

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Services\EmbeddingService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

class BenchmarkSearch extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'search:benchmark {--iterations=10}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Benchmark vector search performance';

    /**
     * Execute the console command.
     */
    public function handle(EmbeddingService $embeddings)
    {
        $this->info('Starting semantic search benchmark...');

        $iterations = (int) $this->option('iterations');

        $user = User::first() ?? User::factory()->create();
        $agent = Agent::first() ?? Agent::factory()->create(['owner_id' => $user->id]);

        $query = 'What is the meaning of life, the universe, and everything?';

        try {
            $queryVector = $embeddings->embed($query);
        } catch (\Exception $e) {
            $this->warn('Could not generate real embeddings. Using a dummy vector for benchmarking.');
            $queryVector = array_fill(0, 1536, 0.1);
        }

        $this->info("Running {$iterations} iterations of search...");

        // Warm up
        Memory::query()->semanticSearch($queryVector, 10)->get();

        $start = microtime(true);
        for ($i = 0; $i < $iterations; $i++) {
            Memory::query()
                ->where('agent_id', $agent->id)
                ->semanticSearch($queryVector, 10)
                ->get();
        }
        $end = microtime(true);

        $totalTime = ($end - $start) * 1000; // ms
        $avgTime = $totalTime / $iterations;

        $this->info('--- Benchmark Results ---');
        $this->info("Total Time ({$iterations} iterations): ".round($totalTime, 2).' ms');
        $this->info('Average Time per Search: '.round($avgTime, 2).' ms');

        // Count total memories in DB to provide context
        $totalMemories = Memory::count();
        $this->info("Total Memories in DB: {$totalMemories}");

        return 0;
    }
}
