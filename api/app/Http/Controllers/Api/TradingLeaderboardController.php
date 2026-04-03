<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\Trade;
use App\Models\TradingStats;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;

class TradingLeaderboardController extends Controller
{
    public function leaderboard(Request $request): JsonResponse
    {
        $paper = filter_var($request->input('paper', 'false'), FILTER_VALIDATE_BOOLEAN);
        $sort = $request->input('sort', 'total_pnl');
        $allowedSorts = ['total_pnl', 'win_rate', 'sharpe_ratio', 'profit_factor'];
        $sort = in_array($sort, $allowedSorts) ? $sort : 'total_pnl';

        $cacheKey = "trading_leaderboard:{$sort}:".($paper ? 'paper' : 'live');

        $entries = Cache::remember($cacheKey, 300, function () use ($paper, $sort) {
            return TradingStats::where('paper', $paper)
                ->where('total_trades', '>', 0)
                ->whereHas('agent', fn ($q) => $q->where('is_listed', true))
                ->orderByDesc($sort)
                ->limit(25)
                ->get()
                ->map(fn (TradingStats $stats) => [
                    'agent_id' => $stats->agent_id,
                    'agent_name' => $stats->agent->name,
                    'total_trades' => (int) $stats->total_trades,
                    'win_rate' => $stats->win_rate === null ? null : (float) $stats->win_rate,
                    'total_pnl' => $stats->total_pnl === null ? null : (float) $stats->total_pnl,
                    'profit_factor' => $stats->profit_factor === null ? null : (float) $stats->profit_factor,
                    'sharpe_ratio' => $stats->sharpe_ratio === null ? null : (float) $stats->sharpe_ratio,
                    'current_streak' => (int) $stats->current_streak,
                ])
                ->toArray();
        });

        return response()->json([
            'type' => 'trading',
            'paper' => $paper,
            'sort' => $sort,
            'entries' => $entries,
        ], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function agentProfile(Request $request, string $agentId): JsonResponse
    {
        $agent = Agent::where('id', $agentId)->where('is_listed', true)->firstOrFail();

        $stats = TradingStats::where('agent_id', $agent->id)->get()->keyBy(fn ($s) => $s->paper ? 'paper' : 'live');

        return response()->json([
            'agent_id' => $agent->id,
            'agent_name' => $agent->name,
            'paper_stats' => $stats->get('paper') ? $stats->get('paper')->toArray() : null,
            'live_stats' => $stats->get('live') ? $stats->get('live')->toArray() : null,
        ], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function agentTrades(Request $request, string $agentId): JsonResponse
    {
        $agent = Agent::where('id', $agentId)->where('is_listed', true)->firstOrFail();

        $paper = filter_var($request->input('paper', 'true'), FILTER_VALIDATE_BOOLEAN);

        $trades = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->whereNull('parent_trade_id')
            ->where('status', 'closed')
            ->with(['decisionMemory' => fn ($q) => $q->where('visibility', 'public')])
            ->orderByDesc('exit_at')
            ->cursorPaginate($request->input('limit', 50));

        return response()->json($trades, 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }
}
