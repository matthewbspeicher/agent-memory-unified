<?php

namespace App\Listeners;

use App\Events\TradeClosed;
use App\Events\TradeOpened;
use App\Jobs\DispatchWebhook;
use App\Models\TradeAlert;
use App\Models\WebhookSubscription;
use Illuminate\Contracts\Queue\ShouldQueue;

class EvaluateTradeAlerts implements ShouldQueue
{
    public function handleTradeOpened(TradeOpened $event): void
    {
        if ($event->trade->paper) {
            return;
        }

        $this->evaluate('trade_opened', $event->trade);
    }

    public function handleTradeClosed(TradeClosed $event): void
    {
        if ($event->trade->paper) {
            return;
        }

        $this->evaluate('trade_closed', $event->trade);

        // Also check PnL-based alerts
        if ($event->trade->pnl !== null) {
            $pnl = (float) $event->trade->pnl;
            if ($pnl > 0) {
                $this->evaluatePnl('pnl_above', $pnl, $event->trade);
            } elseif ($pnl < 0) {  // I15: Change from 'else' to 'elseif' so zero doesn't trigger pnl_below
                $this->evaluatePnl('pnl_below', $pnl, $event->trade);
            }
            // Break-even trades (pnl == 0) trigger neither condition
        }
    }

    private function evaluate(string $condition, $trade): void
    {
        $alerts = TradeAlert::where('agent_id', $trade->agent_id)
            ->where('condition', $condition)
            ->where('is_active', true)
            ->where(function ($q) use ($trade) {
                $q->whereNull('ticker')->orWhere('ticker', $trade->ticker);
            })
            ->get();

        foreach ($alerts as $alert) {
            $this->triggerAlert($alert, $trade);
        }
    }

    private function evaluatePnl(string $condition, float $pnl, $trade): void
    {
        $query = TradeAlert::where('agent_id', $trade->agent_id)
            ->where('condition', $condition)
            ->where('is_active', true)
            ->where(function ($q) use ($trade) {
                $q->whereNull('ticker')->orWhere('ticker', $trade->ticker);
            });

        if ($condition === 'pnl_above') {
            $query->where('threshold', '<=', $pnl);
        } else {
            $query->where('threshold', '>=', $pnl);
        }

        foreach ($query->get() as $alert) {
            $this->triggerAlert($alert, $trade);
        }
    }

    private function triggerAlert(TradeAlert $alert, $trade): void
    {
        $alert->increment('trigger_count');
        $alert->update(['last_triggered_at' => now()]);

        $subscriptions = WebhookSubscription::where('agent_id', $alert->agent_id)
            ->where('is_active', true)
            ->whereJsonContains('events', 'alert.triggered')
            ->get();

        foreach ($subscriptions as $sub) {
            DispatchWebhook::dispatch($sub, 'alert.triggered', [
                'alert_id' => $alert->id,
                'condition' => $alert->condition,
                'ticker' => $trade->ticker ?? null,
                'trade_id' => $trade->id,
                'pnl' => $trade->pnl,
                'direction' => $trade->direction,
                'agent_name' => $trade->agent->name ?? null,
            ]);
        }
    }
}
