<?php

namespace App\Jobs;

use App\Models\Agent;
use App\Services\TradingService;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;

class RecalculateTradingStats implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    /**
     * Create a new job instance.
     */
    public function __construct(
        public Agent $agent,
        public bool $paper
    ) {}

    /**
     * Execute the job.
     */
    public function handle(TradingService $service): void
    {
        $service->recalculateStats($this->agent, $this->paper);
    }
}
