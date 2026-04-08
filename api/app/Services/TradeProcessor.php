<?php

namespace App\Services;

use App\Models\Trade;
use App\ValueObjects\Decimal;
use Illuminate\Support\Facades\DB;

class TradeProcessor
{
    /**
     * Compute PnL for a child trade based on its parent.
     *
     * @return array{pnl: string, pnl_percent: string}
     */
    public function computeChildPnl(Trade $child, Trade $parent): array
    {
        $childEntry = Decimal::from($child->entry_price);
        $parentEntry = Decimal::from($parent->entry_price);
        $childQty = Decimal::from($child->quantity);
        $parentQty = Decimal::from($parent->quantity);

        if ($parent->direction === 'long') {
            // Long entry, short exit: profit when exit > entry
            $grossPnl = $childEntry->sub($parentEntry)->mul($childQty);
        } else {
            // Short entry, long exit: profit when entry > exit
            $grossPnl = $parentEntry->sub($childEntry)->mul($childQty);
        }

        // Apportion parent fee by share of quantity
        $feeShare = Decimal::from($parent->fees)->mul($childQty->div($parentQty));
        $totalFees = $feeShare->add($child->fees);
        $netPnl = $grossPnl->sub($totalFees);

        $costBasis = $parentEntry->mul($childQty);
        $pnlPercent = $costBasis->isGreaterThan('0')
            ? $netPnl->div($costBasis)->mul('100')
            : Decimal::from('0');

        return [
            'pnl' => $netPnl->toString(),
            'pnl_percent' => $pnlPercent->toString(),
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
            $totalChildPnl = Decimal::from($children->sum('pnl'));
            $totalChildQty = Decimal::from($children->sum('quantity'));

            $costBasis = Decimal::from($parent->entry_price)->mul($parent->quantity);
            $parentPnlPercent = $costBasis->isGreaterThan('0')
                ? $totalChildPnl->div($costBasis)->mul('100')
                : Decimal::from('0');

            $parentUpdate = [
                'pnl' => $totalChildPnl->toString(),
                'pnl_percent' => $parentPnlPercent->toString(),
            ];

            // Check if fully closed
            if ($totalChildQty->isGreaterThanOrEqualTo($parent->quantity)) {
                // Weighted average exit price from children
                $weightedExitSum = Decimal::from('0');
                foreach ($children as $c) {
                    $weightedExitSum = $weightedExitSum->add(
                        Decimal::from($c->entry_price)->mul($c->quantity)
                    );
                }
                $weightedExitPrice = $weightedExitSum->div($totalChildQty);

                $parentUpdate['status'] = 'closed';
                $parentUpdate['exit_price'] = $weightedExitPrice->toString();
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
}
