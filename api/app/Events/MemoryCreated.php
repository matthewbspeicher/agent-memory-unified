<?php

namespace App\Events;

use App\Models\Memory;
use Illuminate\Foundation\Events\Dispatchable;

class MemoryCreated
{
    use Dispatchable;

    public function __construct(
        public readonly Memory $memory,
    ) {}
}
