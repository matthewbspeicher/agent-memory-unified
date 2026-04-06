<?php

namespace App\Console\Commands;

use App\Models\Agent;
use App\Models\Trade;
use App\Models\User;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Redis;

class ConsumeTradingEvents extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'trading:consume-events';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Consume trading events from Redis Streams';

    /**
     * Execute the console command.
     */
    public function handle()
    {
        $redis = Redis::connection()->client();
        $stream = 'events';
        $group = 'laravel-api';
        $consumer = 'worker-1';

        try {
            $redis->xGroup('CREATE', $stream, $group, '0', true);
        } catch (\Exception $e) {
            // Group already exists
        }

        $this->info("Listening for trading events on stream: {$stream}...");

        while (true) {
            $messages = $redis->xReadGroup($group, $consumer, [$stream => '>'], 10, 5000);

            if (empty($messages) || !isset($messages[$stream])) {
                continue;
            }

            foreach ($messages[$stream] as $messageId => $messageData) {
                if (!isset($messageData['data'])) {
                    $redis->xAck($stream, $group, [$messageId]);
                    continue;
                }

                $event = json_decode($messageData['data'], true);
                
                if ($event['type'] === 'trade.executed') {
                    $this->info("Processing trade.executed: " . $event['id']);
                    $payload = $event['data'];
                    
                    try {
                        // Ensure system user exists
                        \Illuminate\Support\Facades\DB::table('users')->insertOrIgnore([
                            'id' => 1,
                            'name' => 'System',
                            'email' => 'system@example.com',
                            'password' => bcrypt('password'),
                            'created_at' => now(),
                            'updated_at' => now(),
                        ]);

                        // Ensure agent exists to satisfy foreign key constraints using DB facade
                        \Illuminate\Support\Facades\DB::table('agents')->insertOrIgnore([
                            'id' => $payload['agent_id'],
                            'name' => $payload['agent_name'] ?? 'Unknown Agent',
                            'owner_id' => 1,
                            'created_at' => now(),
                            'updated_at' => now(),
                        ]);

                        Trade::create([
                            'agent_id' => $payload['agent_id'],
                            'ticker' => $payload['symbol'],
                            'direction' => $payload['side'],
                            'entry_price' => $payload['entry_price'],
                            'quantity' => $payload['entry_quantity'],
                            'status' => $payload['status'],
                            'entry_at' => date('Y-m-d H:i:s', strtotime($payload['entry_time'])),
                        ]);
                        $this->info("Successfully created trade record in database!");
                    } catch (\Exception $e) {
                        $this->error("DB Error processing event: " . $e->getMessage());
                    }
                } elseif ($event['type'] === 'memory.consolidation.completed') {
                    $this->info("Processing memory.consolidation.completed");
                    \App\Events\MemoryConsolidationCompleted::dispatch($event['payload']);
                }

                $redis->xAck($stream, $group, [$messageId]);
            }
        }
    }
}
