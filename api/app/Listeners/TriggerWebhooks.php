<?php

namespace App\Listeners;

use App\Events\MemoryShared;
use App\Events\PositionChanged;
use App\Events\TradeClosed;
use App\Events\TradeOpened;
use App\Jobs\DispatchWebhook;
use App\Models\Position;
use App\Models\Trade;
use App\Models\WebhookSubscription;
use Illuminate\Contracts\Queue\ShouldQueue;

class TriggerWebhooks implements ShouldQueue
{
    public function handle(MemoryShared $event): void
    {
        $subscriptions = WebhookSubscription::where('agent_id', $event->recipient->id)
            ->where('is_active', true)
            ->whereJsonContains('events', 'memory.shared')
            ->get();

        $event->memory->loadMissing('agent');

        foreach ($subscriptions as $sub) {
            DispatchWebhook::dispatch($sub, 'memory.shared', [
                'memory_id' => $event->memory->id,
                'memory_key' => $event->memory->key,
                'memory_value' => $event->memory->value,
                'shared_by_agent_id' => $event->memory->agent_id,
                'shared_by_agent_name' => $event->memory->agent->name ?? null,
            ]);
        }
    }

    public function handleTradeOpened(TradeOpened $event): void
    {
        $this->dispatchTradeWebhooks('trade.opened', $event->trade);
    }

    public function handleTradeClosed(TradeClosed $event): void
    {
        $this->dispatchTradeWebhooks('trade.closed', $event->trade);
    }

    public function handlePositionChanged(PositionChanged $event): void
    {
        if ($event->paper || ! $event->agent->is_listed) {
            return;
        }

        $position = Position::where('agent_id', $event->agent->id)
            ->where('ticker', $event->ticker)
            ->where('paper', $event->paper)
            ->first();

        $subscriptions = WebhookSubscription::where('agent_id', $event->agent->id)
            ->where('is_active', true)
            ->whereJsonContains('events', 'position.changed')
            ->get();

        foreach ($subscriptions as $sub) {
            DispatchWebhook::dispatch($sub, 'position.changed', [
                'agent_id' => $event->agent->id,
                'agent_name' => $event->agent->name,
                'ticker' => $event->ticker,
                'paper' => $event->paper,
                'quantity' => $position?->quantity ?? '0.00000000',
                'avg_entry_price' => $position?->avg_entry_price ?? '0.00000000',
            ]);
        }
    }

    private function dispatchTradeWebhooks(string $eventName, Trade $trade): void
    {
        if ($trade->paper || ! $trade->agent->is_listed) {
            return;
        }

        $subscriptions = WebhookSubscription::where('agent_id', $trade->agent_id)
            ->where('is_active', true)
            ->whereJsonContains('events', $eventName)
            ->get();

        foreach ($subscriptions as $sub) {
            DispatchWebhook::dispatch($sub, $eventName, [
                'trade_id' => $trade->id,
                'agent_id' => $trade->agent_id,
                'agent_name' => $trade->agent->name,
                'ticker' => $trade->ticker,
                'direction' => $trade->direction,
                'quantity' => $trade->quantity,
                'entry_price' => $trade->entry_price,
                'exit_price' => $trade->exit_price,
                'pnl' => $trade->pnl,
                'pnl_percent' => $trade->pnl_percent,
                'strategy' => $trade->strategy,
                'status' => $trade->status,
            ]);
        }
    }
}
