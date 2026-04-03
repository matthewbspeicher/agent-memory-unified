<?php

namespace App\Events;

use App\Models\Agent;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class PositionChanged
{
    use Dispatchable, SerializesModels;

    public function __construct(
        public Agent $agent,
        public string $ticker,
        public bool $paper,
    ) {}
}
