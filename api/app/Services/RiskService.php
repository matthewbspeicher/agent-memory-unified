<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Position;
use App\Models\Trade;

class RiskService
{
    public function calculatePositionRisk(Position $position, ?string $marketPrice): array
    {
        $qty = (float) $position->quantity;
        $avgEntry = (float) $position->avg_entry_price;
        $price = $marketPrice !== null ? (float) $marketPrice : $avgEntry;
        $exposure = $price * $qty;
        $unrealizedPnl = ($price - $avgEntry) * $qty;
        $portfolioValue = $position->declared_portfolio_value ? (float) $position->declared_portfolio_value : null;
        $exposurePct = $portfolioValue ? ($exposure / $portfolioValue) * 100 : null;

        return [
            'ticker' => $position->ticker,
            'paper' => (bool) $position->paper,
            'quantity' => (float) $position->quantity,
            'avg_entry_price' => (float) $position->avg_entry_price,
            'market_price' => (float) ($marketPrice ?? $position->avg_entry_price),
            'unrealized_pnl' => round($unrealizedPnl, 8),
            'exposure' => round($exposure, 8),
            'exposure_pct' => $exposurePct !== null ? round($exposurePct, 2) : null,
        ];
    }

    public function calculateMaxDrawdown(Agent $agent, bool $paper): array
    {
        $trades = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->whereNotNull('pnl')
            ->orderBy('exit_at')
            ->pluck('pnl')
            ->map(fn ($v) => (float) $v);

        if ($trades->isEmpty()) {
            return ['max_drawdown' => 0.0, 'peak' => 0.0, 'trough' => 0.0];
        }

        $cumulative = 0;
        $peak = 0;
        $maxDrawdown = 0;
        $trough = 0;

        foreach ($trades as $pnl) {
            $cumulative += $pnl;
            if ($cumulative > $peak) {
                $peak = $cumulative;
            }
            $drawdown = $cumulative - $peak;
            if ($drawdown < $maxDrawdown) {
                $maxDrawdown = $drawdown;
                $trough = $cumulative;
            }
        }

        return [
            'max_drawdown' => round($maxDrawdown, 8),
            'peak' => round($peak, 8),
            'trough' => round($trough, 8),
        ];
    }
}
