<?php

namespace App\Observers;

use App\Events\TradeOpened;
use App\Events\TradeClosed;
use App\Models\Trade;
use AgentMemory\SharedEvents\EventPublisher;
use Illuminate\Support\Facades\Redis;

class TradeObserver
{
    private EventPublisher $publisher;

    public function __construct()
    {
        // Initialize EventPublisher with Redis connection
        $this->publisher = new EventPublisher(
            Redis::connection()->client(),
            'events'
        );
    }

    /**
     * Handle the Trade "created" event.
     */
    public function created(Trade $trade): void
    {
        $this->publisher->publish('TradeOpened', [
            'trade_id' => $trade->id,
            'agent_id' => $trade->agent_id,
            'ticker' => $trade->ticker,
            'direction' => $trade->direction,
            'entry_price' => (string) $trade->entry_price,
            'quantity' => (string) $trade->quantity,
            'status' => $trade->status,
            'paper' => $trade->paper,
        ]);

        // Dispatch Laravel event for internal listeners (webhooks, alerts)
        TradeOpened::dispatch($trade);
    }

    /**
     * Handle the Trade "updated" event.
     */
    public function updated(Trade $trade): void
    {
        // Only publish if trade was closed
        if ($trade->wasChanged('status') && $trade->status === 'closed') {
            $this->publisher->publish('TradeClosed', [
                'trade_id' => $trade->id,
                'agent_id' => $trade->agent_id,
                'ticker' => $trade->ticker,
                'direction' => $trade->direction,
                'entry_price' => (string) $trade->entry_price,
                'exit_price' => (string) $trade->exit_price,
                'quantity' => (string) $trade->quantity,
                'pnl' => (string) $trade->pnl,
                'pnl_percent' => (string) $trade->pnl_percent,
                'status' => $trade->status,
            ]);

            // Dispatch Laravel event for internal listeners (webhooks, alerts)
            TradeClosed::dispatch($trade);
        }
    }
}
