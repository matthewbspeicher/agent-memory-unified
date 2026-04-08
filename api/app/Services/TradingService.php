<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Trade;

/**
 * @deprecated Use TradeProcessor and PositionManager directly.
 */
class TradingService
{
    private TradeProcessor $processor;
    private PositionManager $positionManager;

    public function __construct()
    {
        $this->processor = new TradeProcessor();
        $this->positionManager = new PositionManager();
    }

    public function computeChildPnl(Trade $child, Trade $parent): array
    {
        return $this->processor->computeChildPnl($child, $parent);
    }

    public function processChildTrade(Trade $child, Trade $parent): void
    {
        $this->processor->processChildTrade($child, $parent);
    }

    public function recalculatePosition(Agent $agent, string $ticker, bool $paper): void
    {
        $this->positionManager->recalculatePosition($agent, $ticker, $paper);
    }

    public function recalculateStats(Agent $agent, bool $paper): void
    {
        $this->positionManager->recalculateStats($agent, $paper);
    }
}
