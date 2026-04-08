<?php

namespace App\Listeners;

use App\Events\MemoryCreated;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Support\Facades\Redis;

class PublishMemoryToStream implements ShouldQueue
{
    private const STREAM_KEY = 'memories_indexing_stream';

    public function handle(MemoryCreated $event): void
    {
        $memory = $event->memory;

        Redis::xadd(self::STREAM_KEY, '*', [
            'memory_id' => $memory->id,
            'agent_id' => $memory->agent_id,
            'content' => $memory->value,
        ]);
    }
}
