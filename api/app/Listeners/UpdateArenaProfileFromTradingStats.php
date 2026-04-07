<?php

namespace App\Listeners;

use App\Events\TradingStatsUpdated;
use App\Models\ArenaProfile;
use Illuminate\Contracts\Queue\ShouldQueue;

class UpdateArenaProfileFromTradingStats implements ShouldQueue
{
    public function handle(TradingStatsUpdated $event): void
    {
        // We only update Arena profile based on paper trading stats
        if (! $event->isPaper) {
            return;
        }

        $profile = ArenaProfile::where('agent_id', $event->agent->id)->first();
        
        if ($profile) {
            $stats = $event->stats;
            // Scoring: (Profit Factor * 10) + (Win Rate * 100) + (Sharpe Ratio * 50)
            $pf = (float) ($stats->profit_factor ?? 0);
            $wr = (float) ($stats->win_rate ?? 0) / 100.0; // Win rate as 0-1
            $sr = (float) ($stats->sharpe_ratio ?? 0);
            
            $tradingScore = ($pf * 10) + ($wr * 100) + ($sr * 50);

            $profile->update(['trading_score' => round($tradingScore, 2)]);
        }
    }
}
