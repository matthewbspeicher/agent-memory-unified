<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Trade;

class ReplayService
{
    public function replay(Agent $agent, bool $paper, array $exitOverrides = [], ?float $exitOffsetPct = null): array
    {
        $trades = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->orderBy('exit_at')
            ->get();

        $results = [];
        $totalPnl = 0;
        $wins = 0;
        $losses = 0;
        $cumulative = [];

        foreach ($trades as $trade) {
            $entryPrice = (float) $trade->entry_price;
            $quantity = (float) $trade->quantity;
            $fees = (float) $trade->fees;

            // Determine exit price: override > offset > original
            if (isset($exitOverrides[$trade->ticker])) {
                $exitPrice = (float) $exitOverrides[$trade->ticker];
            } elseif ($exitOffsetPct !== null && $trade->exit_price !== null) {
                $exitPrice = (float) $trade->exit_price * (1 + $exitOffsetPct / 100);
            } else {
                $exitPrice = (float) $trade->exit_price;
            }

            // Compute PnL
            if ($trade->direction === 'long') {
                $pnl = ($exitPrice - $entryPrice) * $quantity - $fees;
            } else {
                $pnl = ($entryPrice - $exitPrice) * $quantity - $fees;
            }

            $totalPnl += $pnl;
            $pnl > 0 ? $wins++ : $losses++;

            $cumulative[] = [
                'trade_id' => $trade->id,
                'ticker' => $trade->ticker,
                'original_pnl' => (float) $trade->pnl,
                'simulated_pnl' => round($pnl, 8),
                'exit_price_used' => round($exitPrice, 8),
                'cumulative_pnl' => round($totalPnl, 8),
            ];
        }

        $total = $wins + $losses;

        return [
            'total_trades' => $total,
            'wins' => $wins,
            'losses' => $losses,
            'win_rate' => $total > 0 ? round(($wins / $total) * 100, 2) : 0,
            'total_pnl' => round($totalPnl, 8),
            'trades' => $cumulative,
        ];
    }
}
