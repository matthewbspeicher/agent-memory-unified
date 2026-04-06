<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Trade;
use Illuminate\Database\Eloquent\Builder;

class TradingStatsService
{
    public function buildStatsQuery(Agent $agent, string $groupBy, bool $paper): Builder
    {
        return Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->whereNotNull($groupBy)
            ->select($groupBy)
            ->selectRaw('COUNT(*) as total_trades')
            ->selectRaw('SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as win_count')
            ->selectRaw('ROUND(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) as win_rate')
            ->selectRaw('SUM(pnl) as total_pnl')
            ->selectRaw('AVG(pnl_percent) as avg_pnl_percent')
            ->selectRaw('CASE WHEN SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) > 0 THEN ROUND(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) / SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END), 4) ELSE NULL END as profit_factor')
            ->groupBy($groupBy)
            ->orderByRaw('SUM(pnl) DESC');
    }
}
