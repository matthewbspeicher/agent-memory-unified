<?php

namespace App\Services;

use App\Models\Achievement;
use App\Models\Agent;
use App\Models\Trade;
use App\Models\TradingStats;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class AchievementService
{
    /**
     * Achievement definitions: slug => [trigger(s), checker method].
     */
    private const DEFINITIONS = [
        'first_memory' => [
            'triggers' => ['store'],
            'checker' => 'checkFirstMemory',
        ],
        'deep_thinker' => [
            'triggers' => ['store'],
            'checker' => 'checkDeepThinker',
        ],
        'librarian' => [
            'triggers' => ['store'],
            'checker' => 'checkLibrarian',
        ],
        'centurion' => [
            'triggers' => ['store'],
            'checker' => 'checkCenturion',
        ],
        'recall_master' => [
            'triggers' => ['search'],
            'checker' => 'checkRecallMaster',
        ],
        'knowledge_sharer' => [
            'triggers' => ['share', 'store'],
            'checker' => 'checkKnowledgeSharer',
        ],
        'session_sage' => [
            'triggers' => ['extract', 'store'],
            'checker' => 'checkSessionSage',
        ],
        'helpful' => [
            'triggers' => ['feedback'],
            'checker' => 'checkHelpful',
        ],
        'first_trade' => [
            'triggers' => ['trade'],
            'checker' => 'checkFirstTrade',
        ],
        'first_win' => [
            'triggers' => ['trade'],
            'checker' => 'checkFirstWin',
        ],
        'streak_5' => [
            'triggers' => ['trade'],
            'checker' => 'checkStreak5',
        ],
        'century_club' => [
            'triggers' => ['trade'],
            'checker' => 'checkCenturyClub',
        ],
        'sharp_shooter' => [
            'triggers' => ['trade'],
            'checker' => 'checkSharpShooter',
        ],
        'streak_10' => [
            'triggers' => ['trade'],
            'checker' => 'checkStreak10',
        ],
        'risk_manager' => [
            'triggers' => ['trade'],
            'checker' => 'checkRiskManager',
        ],
        'profit_machine' => [
            'triggers' => ['trade'],
            'checker' => 'checkProfitMachine',
        ],
    ];

    /**
     * Check all achievements for a given trigger and award any that are newly earned.
     */
    public function checkAndAward(Agent $agent, string $trigger): void
    {
        try {
            foreach (self::DEFINITIONS as $slug => $definition) {
                if (! in_array($trigger, $definition['triggers'])) {
                    continue;
                }

                if ($this->alreadyAwarded($agent, $slug)) {
                    continue;
                }

                $checker = $definition['checker'];
                if ($this->$checker($agent)) {
                    $this->award($agent, $slug);
                }
            }
        } catch (\Throwable $e) {
            Log::warning('Achievement check failed', [
                'agent_id' => $agent->id,
                'trigger' => $trigger,
                'error' => $e->getMessage(),
            ]);
        }
    }

    /**
     * Check and award early_adopter achievement (special: time-based, not trigger-based).
     */
    public function checkEarlyAdopter(Agent $agent): bool
    {
        try {
            if ($this->alreadyAwarded($agent, 'early_adopter')) {
                return false;
            }

            $launchDate = config('app.launch_date');
            if (! $launchDate) {
                return false;
            }

            $launch = Carbon::parse($launchDate);
            $cutoff = $launch->copy()->addDays(7);

            if (now()->lte($cutoff)) {
                $this->award($agent, 'early_adopter');

                return true;
            }

            return false;
        } catch (\Throwable $e) {
            Log::warning('Early adopter check failed', [
                'agent_id' => $agent->id,
                'error' => $e->getMessage(),
            ]);

            return false;
        }
    }

    private function alreadyAwarded(Agent $agent, string $slug): bool
    {
        return Achievement::where('agent_id', $agent->id)
            ->where('achievement_slug', $slug)
            ->exists();
    }

    private function award(Agent $agent, string $slug): void
    {
        Achievement::create([
            'agent_id' => $agent->id,
            'achievement_slug' => $slug,
            'earned_at' => now(),
        ]);
    }

    // -------------------------------------------------------------------------
    // Checker methods
    // -------------------------------------------------------------------------

    private function checkFirstMemory(Agent $agent): bool
    {
        return $agent->memories()->count() >= 1;
    }

    private function checkDeepThinker(Agent $agent): bool
    {
        return $agent->memories()->where('importance', '>=', 8)->count() >= 50;
    }

    private function checkLibrarian(Agent $agent): bool
    {
        return $agent->memories()->whereNotNull('category')->count() >= 100;
    }

    private function checkCenturion(Agent $agent): bool
    {
        return $agent->memories()->count() >= 1000;
    }

    private function checkRecallMaster(Agent $agent): bool
    {
        // Try activity log first (Task 5), fall back to access_count sum
        try {
            $searchCount = DB::table('agent_activity_log')
                ->where('agent_id', $agent->id)
                ->where('action', 'search')
                ->count();

            return $searchCount >= 100;
        } catch (\Throwable $e) {
            // Table doesn't exist yet — fall back to access_count sum
            return (int) $agent->memories()->sum('access_count') >= 100;
        }
    }

    private function checkKnowledgeSharer(Agent $agent): bool
    {
        return $agent->memories()->where('visibility', 'public')->count() >= 10;
    }

    private function checkSessionSage(Agent $agent): bool
    {
        return $agent->memories()->where('category', 'session-extraction')->count() >= 10;
    }

    private function checkHelpful(Agent $agent): bool
    {
        return (int) $agent->memories()
            ->where('visibility', 'public')
            ->sum('useful_count') >= 50;
    }

    private function checkFirstTrade(Agent $agent): bool
    {
        return Trade::where('agent_id', $agent->id)->count() >= 1;
    }

    private function checkFirstWin(Agent $agent): bool
    {
        return Trade::where('agent_id', $agent->id)
            ->where('status', 'closed')
            ->whereNull('parent_trade_id')
            ->where('pnl', '>', 0)
            ->exists();
    }

    private function checkStreak5(Agent $agent): bool
    {
        $stats = TradingStats::where('agent_id', $agent->id)->first();

        return $stats && $stats->current_streak >= 5;
    }

    private function checkCenturyClub(Agent $agent): bool
    {
        return Trade::where('agent_id', $agent->id)
            ->whereNull('parent_trade_id')
            ->count() >= 100;
    }

    private function checkSharpShooter(Agent $agent): bool
    {
        $stats = TradingStats::where('agent_id', $agent->id)->first();

        return $stats && $stats->total_trades >= 20 && (float) $stats->win_rate > 70.0;
    }

    private function checkStreak10(Agent $agent): bool
    {
        $stats = TradingStats::where('agent_id', $agent->id)->first();

        return $stats && $stats->current_streak >= 10;
    }

    private function checkRiskManager(Agent $agent): bool
    {
        $stats = TradingStats::where('agent_id', $agent->id)->first();

        return $stats && $stats->total_trades >= 30 && (float) $stats->sharpe_ratio > 2.0;
    }

    private function checkProfitMachine(Agent $agent): bool
    {
        $stats = TradingStats::where('agent_id', $agent->id)->first();

        return $stats && $stats->total_trades >= 20 && (float) $stats->profit_factor > 3.0;
    }
}
