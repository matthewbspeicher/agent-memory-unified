<?php

namespace App\Events;

use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Foundation\Events\Dispatchable;

class MemoryShared
{
    use Dispatchable;

    public function __construct(
        public Memory $memory,
        public Agent $recipient
    ) {}
}
