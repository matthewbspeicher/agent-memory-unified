<?php

namespace App\Console\Commands;

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use App\Services\EmbeddingService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

class EvaluateSearchAccuracy extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'search:evaluate {--limit=10}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Evaluate semantic search accuracy using a baseline dataset';

    /**
     * Execute the console command.
     */
    public function handle(EmbeddingService $embeddings)
    {
        $this->info('Starting semantic search evaluation...');

        // Check if Gemini key is set
        if (! config('services.gemini.key')) {
            $this->error('Gemini API key is missing. Required for generating real embeddings.');

            return 1;
        }

        $dataset = [
            'corpus' => [
                'doc1' => 'The quick brown fox jumps over the lazy dog.',
                'doc2' => 'Laravel is a web application framework with expressive, elegant syntax.',
                'doc3' => 'PostgreSQL is a powerful, open source object-relational database system.',
                'doc4' => 'Redis is an in-memory data structure store, used as a distributed, in-memory key–value database.',
                'doc5' => 'Artificial intelligence is the intelligence of machines or software.',
                'doc6' => 'A user can authenticate via magic links sent to their email address.',
                'doc7' => 'To improve database performance, use proper indexing such as B-tree or GIN.',
                'doc8' => 'Semantic search relies on vector embeddings to find meaning rather than exact keywords.',
                'doc9' => 'Docker allows you to package an application with all of its dependencies into a standardized unit.',
                'doc10' => 'The sky is blue because molecules in the air scatter blue light from the sun more than they scatter red light.',
            ],
            'queries' => [
                [
                    'q' => 'How does a person log in?',
                    'expected' => 'doc6',
                ],
                [
                    'q' => 'What color is the sky?',
                    'expected' => 'doc10',
                ],
                [
                    'q' => 'What is Laravel?',
                    'expected' => 'doc2',
                ],
                [
                    'q' => 'How does meaning-based search work?',
                    'expected' => 'doc8',
                ],
                [
                    'q' => 'Tell me about machine smarts.',
                    'expected' => 'doc5',
                ],
            ],
        ];

        DB::beginTransaction();
        try {
            $user = User::factory()->create();
            $agent = Agent::factory()->create(['owner_id' => $user->id]);

            $this->info('Embedding and indexing corpus...');

            $docsToEmbed = array_values($dataset['corpus']);
            $keys = array_keys($dataset['corpus']);

            // Get embeddings for all corpus docs at once to save time
            $vectors = $embeddings->embedBatch($docsToEmbed);

            foreach ($keys as $index => $key) {
                Memory::create([
                    'agent_id' => $agent->id,
                    'key' => $key,
                    'value' => $dataset['corpus'][$key],
                    'embedding' => '['.implode(',', $vectors[$index]).']',
                    'visibility' => 'private',
                ]);
            }

            $this->info('Running evaluation queries...');

            $limit = (int) $this->option('limit');

            $score = 0;
            $mrr = 0.0;
            $total = count($dataset['queries']);

            foreach ($dataset['queries'] as $query) {
                $q = $query['q'];
                $expected = $query['expected'];

                $queryVector = $embeddings->embed($q);

                $results = Memory::query()
                    ->where('agent_id', $agent->id)
                    ->semanticSearch($queryVector, $limit)
                    ->get();

                $rank = null;
                foreach ($results as $index => $result) {
                    if ($result->key === $expected) {
                        $rank = $index + 1;
                        break;
                    }
                }

                if ($rank !== null) {
                    $mrr += (1 / $rank);
                    if ($rank === 1) {
                        $score++;
                    }
                    $this->line("✅ Query: '{$q}' -> Expected '{$expected}' found at rank {$rank}");
                } else {
                    $this->error("❌ Query: '{$q}' -> Expected '{$expected}' NOT FOUND in top {$limit}");
                }
            }

            $this->info('--- Evaluation Results ---');
            $this->info('Top-1 Accuracy: '.round(($score / $total) * 100, 2)."% ($score/$total)");
            $this->info('MRR (Mean Reciprocal Rank): '.round($mrr / $total, 4));

            // Rollback to clean up database
            DB::rollBack();
            $this->info('Database rolled back successfully.');

        } catch (\Exception $e) {
            DB::rollBack();
            $this->error('Evaluation failed: '.$e->getMessage());

            return 1;
        }

        return 0;
    }
}
