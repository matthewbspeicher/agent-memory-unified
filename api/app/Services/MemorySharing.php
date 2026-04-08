<?php

namespace App\Services;

use App\Events\MemoryShared;
use App\Models\Agent;
use App\Models\Memory;

class MemorySharing
{
    public function shareWith(Memory $memory, Agent $recipient): void
    {
        $memory->sharedWith()->syncWithoutDetaching([$recipient->id]);
        MemoryShared::dispatch($memory, $recipient);
    }

    public function revokeShare(Memory $memory, Agent $recipient): void
    {
        $memory->sharedWith()->detach($recipient->id);
    }
}
