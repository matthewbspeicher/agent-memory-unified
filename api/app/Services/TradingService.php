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
            $totalChildPnl = $parent->children()->sum('pnl');
            $totalChildQty = $parent->children()->sum('quantity');

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
                foreach ($parent->children as $c) {
                    $weightedExitSum = bcadd($weightedExitSum, bcmul($c->entry_price, $c->quantity, 8), 8);
                }
                $weightedExitPrice = bcdiv($weightedExitSum, (string) $totalChildQty, 8);

                $parentUpdate['status'] = 'closed';
                $parentUpdate['exit_price'] = $weightedExitPrice;
                $parentUpdate['exit_at'] = $child->entry_at;
            }

            $parent->updateQuietly($parentUpdate);
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
        $closedTrades = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->orderBy('entry_at')
            ->get();

        $totalTrades = $closedTrades->count();

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

        $winCount = $closedTrades->filter(fn ($t) => bccomp($t->pnl, '0', 8) > 0)->count();
        $lossCount = $closedTrades->filter(fn ($t) => bccomp($t->pnl, '0', 8) < 0)->count();
        $winRate = round(($winCount / $totalTrades) * 100, 2);

        $totalPnl = $closedTrades->reduce(fn ($carry, $t) => bcadd($carry ?? '0', $t->pnl, 8), '0');
        $avgPnlPercent = $closedTrades->avg('pnl_percent');

        $grossProfit = $closedTrades
            ->filter(fn ($t) => bccomp($t->pnl, '0', 8) > 0)
            ->reduce(fn ($carry, $t) => bcadd($carry ?? '0', $t->pnl, 8), '0');

        $grossLoss = $closedTrades
            ->filter(fn ($t) => bccomp($t->pnl, '0', 8) < 0)
            ->reduce(fn ($carry, $t) => bcadd($carry ?? '0', $t->pnl, 8), '0');

        $absGrossLoss = bcmul($grossLoss, '-1', 8);
        $profitFactor = bccomp($absGrossLoss, '0', 8) > 0
            ? bcdiv($grossProfit, $absGrossLoss, 4)
            : null;

        $bestPnl = $closedTrades->max('pnl');
        $worstPnl = $closedTrades->min('pnl');

        // Current streak: iterate from most recent
        $streak = 0;
        $reversed = $closedTrades->reverse();
        $streakDirection = null;
        foreach ($reversed as $trade) {
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

        // Sharpe ratio (annualized, if >= 30 trades)
        $sharpe = null;
        if ($totalTrades >= 30) {
            $returns = $closedTrades->pluck('pnl_percent')->map(fn ($v) => (float) $v);
            $avgReturn = $returns->avg();
            $stdDev = sqrt($returns->map(fn ($r) => pow($r - $avgReturn, 2))->avg());
            if ($stdDev > 0) {
                $sharpe = round(($avgReturn / $stdDev) * sqrt(252), 4);
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

        // Update Trading Gym score in Arena Profile if it exists
        if ($paper) {
            $profile = ArenaProfile::where('agent_id', $agent->id)->first();
            if ($profile) {
                // Scoring: (Profit Factor * 10) + (Win Rate * 100) + (Sharpe Ratio * 50)
                $pf = (float) ($stats->profit_factor ?? 0);
                $wr = (float) ($stats->win_rate ?? 0) / 100.0; // Win rate as 0-1
                $sr = (float) ($stats->sharpe_ratio ?? 0);
                
                $tradingScore = ($pf * 10) + ($wr * 100) + ($sr * 50);
                
                // We use the existing global_elo column for the score if we're in a Trading Gym
                // Or we could have a dedicated column. For now, let's just update the profile's
                // T4: Use dedicated column instead of personality_tags hack
                $tradingScore = ($profitFactor * 10) + ($winRate * 100) + ($sharpeRatio * 50);
                $profile->update(['trading_score' => round($tradingScore, 2)]);
            }
        }
    }
}
