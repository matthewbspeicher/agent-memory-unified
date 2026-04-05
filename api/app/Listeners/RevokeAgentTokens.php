<?php

namespace App\Listeners;

use App\Events\AgentDeactivated;
use Illuminate\Support\Facades\Redis;
use Illuminate\Support\Facades\Log;

/**
 * Revoke all tokens for an agent by adding wildcard to Redis blacklist.
 *
 * This prevents both JWT and legacy tokens from being used.
 * Pattern: revoked_tokens:{agent_id} → add "*" member
 */
class RevokeAgentTokens
{
    public function handle(AgentDeactivated $event): void
    {
        $agentId = $event->agent->id;

        try {
            $redis = Redis::connection()->client();

            // Add wildcard to revocation set
            // This matches all tokens for this agent (JWT and legacy)
            $redis->sadd("revoked_tokens:{$agentId}", '*');

            // Optional: Publish event to Redis pub/sub for Python consumer
            // (Currently not needed since shared Redis blacklist is immediate)
            if (config('app.enable_event_bridge', false)) {
                $redis->publish('laravel-events', json_encode([
                    'type' => 'AgentDeactivated',
                    'data' => [
                        'agent_id' => $agentId,
                        'agent_name' => $event->agent->name,
                        'timestamp' => now()->toIso8601String(),
                    ],
                ]));
            }

            Log::info("Revoked all tokens for agent", [
                'agent_id' => $agentId,
                'agent_name' => $event->agent->name,
            ]);
        } catch (\Throwable $e) {
            // Log but don't fail the deactivation
            Log::error("Failed to revoke agent tokens", [
                'agent_id' => $agentId,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
