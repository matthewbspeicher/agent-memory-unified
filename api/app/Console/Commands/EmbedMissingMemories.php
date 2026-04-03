<?php

namespace App\Console\Commands;

use App\Models\Memory;
use App\Services\EmbeddingService;
use Illuminate\Console\Command;

class EmbedMissingMemories extends Command
{
    protected $signature = 'memories:embed-missing {--batch=50 : Batch size}';

    protected $description = 'Generate embeddings for memories that are missing them';

    public function handle(EmbeddingService $embeddings): int
    {
        $batchSize = (int) $this->option('batch');
        $total = Memory::whereNull('embedding')->count();

        if ($total === 0) {
            $this->info('No memories missing embeddings.');

            return 0;
        }

        $this->info("Found {$total} memories missing embeddings. Processing in batches of {$batchSize}...");
        $processed = 0;

        Memory::whereNull('embedding')
            ->chunkById($batchSize, function ($memories) use ($embeddings, &$processed) {
                $values = $memories->pluck('value')->toArray();
                $vectors = $embeddings->embedBatch($values);

                foreach ($memories as $i => $memory) {
                    if (isset($vectors[$i])) {
                        $memory->update(['embedding' => $vectors[$i]]);
                        $processed++;
                    }
                }

                $this->info("  Processed {$processed} memories...");
            });

        $this->info("Done. Embedded {$processed} memories.");

        return 0;
    }
}
