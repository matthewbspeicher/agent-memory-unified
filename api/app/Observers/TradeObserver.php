<?php

namespace App\Observers;

use App\Events\PositionChanged;
use App\Events\TradeClosed;
use App\Events\TradeOpened;
use App\Jobs\RecalculateTradingStats;
use App\Models\Trade;
use App\Services\AchievementService;
use App\Services\TradingService;

class TradeObserver
{
    public function __construct(
        private readonly TradingService $tradingService,
        private readonly AchievementService $achievements,
    ) {}

    public function created(Trade $trade): void
    {
        if ($trade->parent_trade_id) {
            $parent = $trade->parentTrade;
            $this->tradingService->processChildTrade($trade, $parent);
            RecalculateTradingStats::dispatch($trade->agent, $trade->paper);

            // Fire TradeClosed if parent is now closed
            $parent->refresh();
            if ($parent->status === 'closed') {
                TradeClosed::dispatch($parent);
            }
        } else {
            // New parent entry trade
            TradeOpened::dispatch($trade);
        }

        $this->tradingService->recalculatePosition(
            $trade->agent,
            $trade->ticker,
            $trade->paper,
        );

        PositionChanged::dispatch($trade->agent, $trade->ticker, $trade->paper);

        $this->achievements->checkAndAward($trade->agent, 'trade');
    }

    public function updated(Trade $trade): void
    {
        if ($trade->wasChanged('status') && $trade->status === 'cancelled') {
            $this->tradingService->recalculatePosition(
                $trade->agent,
                $trade->ticker,
                $trade->paper,
            );

            RecalculateTradingStats::dispatch($trade->agent, $trade->paper);
        }
    }
}
