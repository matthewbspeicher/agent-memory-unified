<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Position;
use App\Models\Trade;
use App\Models\TradingStats;
use App\Models\ArenaProfile;
use Illuminate\Support\Facades\DB;

class TradingService
{
    /**
     * Compute PnL for a child trade based on its parent.
     *
     * @return array{pnl: string, pnl_percent: string}
     */
    public function computeChildPnl(Trade $child, Trade $parent): array
    {
        if ($parent->direction === 'long') {
            // Long entry, short exit: profit when exit > entry
            $grossPnl = bcmul(bcsub($child->entry_price, $parent->entry_price, 8), $child->quantity, 8);
        } else {
            // Short entry, long exit: profit when entry > exit
            $grossPnl = bcmul(bcsub($parent->entry_price, $child->entry_price, 8), $child->quantity, 8);
        }

        // Apportion parent fee by share of quantity
        $feeShare = bcmul(
            $parent->fees,
            bcdiv($child->quantity, $parent->quantity, 8),
            8
        );
        $totalFees = bcadd($feeShare, $child->fees, 8);
        $netPnl = bcsub($grossPnl, $totalFees, 8);

        $costBasis = bcmul($parent->entry_price, $child->quantity, 8);
        $pnlPercent = $costBasis > 0
            ? bcmul(bcdiv($netPnl, $costBasis, 8), '100', 4)
            : '0.0000';

        return [
            'pnl' => $netPnl,
            'pnl_percent' => $pnlPercent,
        ];
    }

    /**
     * After a child trade is created, update the parent with aggregated PnL
     * and potentially close it.
     */
    public function processChildTrade(Trade $child, Trade $parent): void
    {
        DB::transaction(function () use ($child, $parent) {
            $pnl = $this->computeChildPnl($child, $parent);

            $child->updateQuietly([
                'pnl' => $pnl['pnl'],
                'pnl_percent' => $pnl['pnl_percent'],
            ]);

            // Aggregate PnL across all children onto parent
            // Load the children once
            $children = $parent->children()->get();
            $totalChildPnl = $children->sum('pnl');
            $totalChildQty = $children->sum('quantity');

            $costBasis = bcmul($parent->entry_price, $parent->quantity, 8);
            $parentPnlPercent = $costBasis > 0
                ? bcmul(bcdiv((string) $totalChildPnl, $costBasis, 8), '100', 4)
                : '0.0000';

            $parentUpdate = [
                'pnl' => (string) $totalChildPnl,
                'pnl_percent' => $parentPnlPercent,
            ];

            // Check if fully closed
            if (bccomp((string) $totalChildQty, $parent->quantity, 8) >= 0) {
                // Weighted average exit price from children
                $weightedExitSum = '0';
                foreach ($children as $c) {
                    $weightedExitSum = bcadd($weightedExitSum, bcmul($c->entry_price, $c->quantity, 8), 8);
                }
                $weightedExitPrice = bcdiv($weightedExitSum, (string) $totalChildQty, 8);

                $parentUpdate['status'] = 'closed';
                $parentUpdate['exit_price'] = $weightedExitPrice;
                $parentUpdate['exit_at'] = $child->entry_at;
            }

            $parent->updateQuietly($parentUpdate);

            // If the parent was fully closed, dispatch the event manually
            // since updateQuietly bypasses the Observer
            if (isset($parentUpdate['status']) && $parentUpdate['status'] === 'closed') {
                event(new \App\Events\TradeClosed($parent->fresh()));
            }
        });
    }

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

        $totalQty = '0';
        $totalCost = '0';

        /** @var \App\Models\Trade $entry */
        foreach ($openEntries as $entry) {
            $remainingQty = $entry->remainingQuantity();
            $totalQty = bcadd($totalQty, $remainingQty, 8);
            $totalCost = bcadd($totalCost, bcmul($entry->entry_price, $remainingQty, 8), 8);
        }

        $avgPrice = bccomp($totalQty, '0', 8) > 0
            ? bcdiv($totalCost, $totalQty, 8)
            : '0.00000000';

        Position::updateOrCreate(
            [
                'agent_id' => $agent->id,
                'ticker' => $ticker,
                'paper' => $paper,
            ],
            [
                'quantity' => $totalQty,
                'avg_entry_price' => $avgPrice,
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
