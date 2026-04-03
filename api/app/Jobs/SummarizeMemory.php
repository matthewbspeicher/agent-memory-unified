<?php

namespace App\Jobs;

use App\Models\Memory;
use App\Services\SummarizationService;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;

class SummarizeMemory implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    /**
     * Create a new job instance.
     */
    public function __construct(
        public Memory $memory
    ) {}

    /**
     * Execute the job.
     */
    public function handle(SummarizationService $summarizer): void
    {
        if ($this->memory->summary) {
            return;
        }

        try {
            $summary = $summarizer->generateSummary($this->memory->value);
            
            if ($summary) {
                $this->memory->update(['summary' => $summary]);
            }
        } catch (\Exception $e) {
            Log::error('Summarization job failed', [
                'memory_id' => $this->memory->id,
                'error' => $e->getMessage()
            ]);
            
            throw $e;
        }
    }
}
