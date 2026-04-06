<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use Illuminate\Support\Facades\Redis;

class EventHealthController extends Controller
{
    public function __invoke()
    {
        $streamKey = 'agent_memory_events';
        $consumerGroup = 'trading_bot';

        try {
            $redis = Redis::connection();

            // Check Redis connectivity
            $redis->ping();

            // Stream info
            $streamExists = (bool) $redis->exists($streamKey);
            $streamLength = $streamExists ? $redis->xlen($streamKey) : 0;

            // Consumer group info
            $groups = [];
            if ($streamExists) {
                try {
                    $groupInfo = $redis->xinfo('GROUPS', $streamKey);
                    foreach ($groupInfo as $group) {
                        $groups[] = [
                            'name' => $group['name'] ?? $group[1] ?? 'unknown',
                            'consumers' => $group['consumers'] ?? $group[3] ?? 0,
                            'pending' => $group['pending'] ?? $group[5] ?? 0,
                            'last_delivered_id' => $group['last-delivered-id'] ?? $group[7] ?? '0-0',
                        ];
                    }
                } catch (\Throwable) {
                    // Group may not exist yet — that's ok
                }
            }

            return response()->json([
                'status' => 'healthy',
                'redis' => 'connected',
                'stream' => [
                    'key' => $streamKey,
                    'exists' => $streamExists,
                    'length' => $streamLength,
                ],
                'consumer_groups' => $groups,
                'checked_at' => now()->toIso8601String(),
            ]);
        } catch (\Throwable $e) {
            return response()->json([
                'status' => 'unhealthy',
                'redis' => 'disconnected',
                'error' => $e->getMessage(),
                'checked_at' => now()->toIso8601String(),
            ], 503);
        }
    }
}
