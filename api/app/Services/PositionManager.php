<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Position;
use App\Models\Trade;
use App\Models\TradingStats;
use App\ValueObjects\Decimal;

class PositionManager
{
    /**
     * Recalculate the position for a given agent/ticker/paper combo.
     */
    public function recalculatePosition(Agent $agent, string $ticker, bool $paper): void
    {
        $openEntries = Trade::where('agent_id', $agent->id)
            ->where('ticker', $ticker)
            ->where('paper', $paper)
            ->where('status', 'open')
            ->whereNull('parent_trade_id')
            ->get();

        if ($openEntries->isEmpty()) {
            Position::where('agent_id', $agent->id)
                ->where('ticker', $ticker)
                ->where('paper', $paper)
                ->delete();

            return;
        }

        $totalQty = Decimal::from('0');
        $totalCost = Decimal::from('0');

        /** @var \App\Models\Trade $entry */
        foreach ($openEntries as $entry) {
            $remainingQty = Decimal::from($entry->remainingQuantity());
            $totalQty = $totalQty->add($remainingQty);
            $totalCost = $totalCost->add(Decimal::from($entry->entry_price)->mul($remainingQty));
        }

        $avgPrice = $totalQty->isGreaterThan('0')
            ? $totalCost->div($totalQty)
            : Decimal::from('0');

        Position::updateOrCreate(
            [
                'agent_id' => $agent->id,
                'ticker' => $ticker,
                'paper' => $paper,
            ],
            [
                'quantity' => $totalQty->toString(),
                'avg_entry_price' => $avgPrice->toString(),
            ]
        );
    }

    /**
     * Recalculate aggregate trading stats for an agent.
     */
    public function recalculateStats(Agent $agent, bool $paper): void
    {
        // Compute metrics directly on DB to avoid memory exhaustion
        $statsData = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->selectRaw('COUNT(*) as total_trades')
            ->selectRaw('SUM(CASE WHEN CAST(pnl AS numeric) > 0 THEN 1 ELSE 0 END) as win_count')
            ->selectRaw('SUM(CASE WHEN CAST(pnl AS numeric) < 0 THEN 1 ELSE 0 END) as loss_count')
            ->selectRaw('SUM(CAST(pnl AS numeric)) as total_pnl')
            ->selectRaw('AVG(CAST(pnl_percent AS numeric)) as avg_pnl_percent')
            ->selectRaw('MAX(CAST(pnl AS numeric)) as best_trade_pnl')
            ->selectRaw('MIN(CAST(pnl AS numeric)) as worst_trade_pnl')
            ->first();

        $totalTrades = (int) ($statsData->total_trades ?? 0);

        if ($totalTrades === 0) {
            TradingStats::updateOrCreate(
                ['agent_id' => $agent->id, 'paper' => $paper],
                [
                    'total_trades' => 0,
                    'win_count' => 0,
                    'loss_count' => 0,
                    'win_rate' => null,
                    'profit_factor' => null,
                    'total_pnl' => 0,
                    'avg_pnl_percent' => null,
                    'best_trade_pnl' => null,
                    'worst_trade_pnl' => null,
                    'sharpe_ratio' => null,
                    'current_streak' => 0,
                ]
            );

            return;
        }

        $winCount = (int) ($statsData->win_count ?? 0);
        $lossCount = (int) ($statsData->loss_count ?? 0);
        $winRate = round(($winCount / $totalTrades) * 100, 2);

        $totalPnl = (string) ($statsData->total_pnl ?? '0');
        $avgPnlPercent = (float) ($statsData->avg_pnl_percent ?? 0.0);
        $bestPnl = (string) ($statsData->best_trade_pnl ?? '0');
        $worstPnl = (string) ($statsData->worst_trade_pnl ?? '0');

        $grossProfitObj = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->whereRaw('CAST(pnl AS numeric) > 0')
            ->selectRaw('SUM(CAST(pnl AS numeric)) as gross_profit')
            ->first();
        $grossProfit = $grossProfitObj->gross_profit ?? 0;

        $grossLossObj = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->whereRaw('CAST(pnl AS numeric) < 0')
            ->selectRaw('SUM(CAST(pnl AS numeric)) as gross_loss')
            ->first();
        $grossLoss = $grossLossObj->gross_loss ?? 0;

        $profitFactor = null;
        if ($grossLoss < 0) {
            $profitFactor = round($grossProfit / abs($grossLoss), 4);
        } elseif ($grossProfit > 0) {
            $profitFactor = 999.99; // Or something
        }

        // Streak requires sequence order. Getting just Win/Loss from DB is lighter.
        // We can fetch only the PnL values and order by entry_at desc
        $streakTrades = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->orderByDesc('entry_at')
            ->select('pnl', 'pnl_percent')
            ->get();
        
        $streak = 0;
        $streakDirection = null;
        foreach ($streakTrades as $trade) {
            $isWin = bccomp($trade->pnl, '0', 8) > 0;
            if ($streakDirection === null) {
                $streakDirection = $isWin;
            }
            if ($isWin === $streakDirection) {
                $streak++;
            } else {
                break;
            }
        }
        if ($streakDirection === false) {
            $streak = -$streak;
        }

        // Sharpe Ratio
        $sharpe = null;
        if ($totalTrades >= 30) {
            // Need all returns for standard deviation
            $returns = $streakTrades->pluck('pnl_percent')->map(fn ($v) => (float) $v);
            $avgReturn = $returns->avg();
            if ($returns->count() > 0) {
                $stdDev = sqrt($returns->map(fn ($r) => pow($r - $avgReturn, 2))->avg());
                if ($stdDev > 0) {
                    $sharpe = round(($avgReturn / $stdDev) * sqrt(252), 4);
                }
            }
        }

        $stats = TradingStats::updateOrCreate(
            ['agent_id' => $agent->id, 'paper' => $paper],
            [
                'total_trades' => $totalTrades,
                'win_count' => $winCount,
                'loss_count' => $lossCount,
                'win_rate' => $winRate,
                'profit_factor' => $profitFactor,
                'total_pnl' => $totalPnl,
                'avg_pnl_percent' => round($avgPnlPercent, 4),
                'best_trade_pnl' => $bestPnl,
                'worst_trade_pnl' => $worstPnl,
                'sharpe_ratio' => $sharpe,
                'current_streak' => $streak,
            ]
        );

        \App\Events\TradingStatsUpdated::dispatch($agent, $stats, $paper);
    }
}
