<?php

namespace App\Events;

use App\Models\Agent;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

/**
 * Dispatched when an agent is deactivated.
 *
 * Triggers token revocation by adding wildcard to Redis blacklist.
 */
class AgentDeactivated
{
    use Dispatchable, InteractsWithSockets, SerializesModels;

    public function __construct(
        public Agent $agent
    ) {}
}
