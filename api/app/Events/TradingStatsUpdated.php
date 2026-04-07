<?php

namespace App\Events;

use App\Models\Agent;
use App\Models\TradingStats;
use Illuminate\Foundation\Events\Dispatchable;

class TradingStatsUpdated
{
    use Dispatchable;

    public function __construct(
        public readonly Agent $agent,
        public readonly TradingStats $stats,
        public readonly bool $isPaper
    ) {}
}
