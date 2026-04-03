<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\Position;
use App\Models\TradingStats;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class PortfolioController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $paper = filter_var($request->input('paper', false), FILTER_VALIDATE_BOOLEAN);
        $agent = $request->attributes->get('agent');
        $ownerId = $agent->owner_id;

        $agentIds = Agent::where('owner_id', $ownerId)->pluck('id');

        // Aggregate positions by ticker
        $positions = Position::whereIn('agent_id', $agentIds)
            ->where('paper', $paper)
            ->get()
            ->groupBy('ticker')
            ->map(function ($group, $ticker) {
                $totalQty = $group->sum(fn ($p) => (float) $p->quantity);
                $weightedPrice = $group->sum(fn ($p) => (float) $p->quantity * (float) $p->avg_entry_price);

                return [
                    'ticker' => $ticker,
                    'total_quantity' => round($totalQty, 8),
                    'avg_entry_price' => $totalQty > 0 ? round($weightedPrice / $totalQty, 8) : 0,
                    'agent_count' => $group->count(),
                ];
            })
            ->values();

        // Aggregate stats
        $stats = TradingStats::whereIn('agent_id', $agentIds)
            ->where('paper', $paper)
            ->get();

        $aggregateStats = [
            'total_trades' => $stats->sum('total_trades'),
            'win_count' => $stats->sum('win_count'),
            'loss_count' => $stats->sum('loss_count'),
            'total_pnl' => round($stats->sum(fn ($s) => (float) $s->total_pnl), 8),
            'agent_count' => $agentIds->count(),
        ];

        // Per-agent breakdown
        $agentBreakdown = Agent::whereIn('id', $agentIds)
            ->with(['tradingStats' => fn ($q) => $q->where('paper', $paper)])
            ->get()
            ->map(fn ($a) => [
                'agent_id' => $a->id,
                'agent_name' => $a->name,
                'total_pnl' => (float) ($a->tradingStats->first()?->total_pnl ?? 0),
                'total_trades' => $a->tradingStats->first()?->total_trades ?? 0,
                'win_rate' => (float) ($a->tradingStats->first()?->win_rate ?? 0),
            ]);

        return response()->json([
            'data' => [
                'positions' => $positions,
                'aggregate_stats' => $aggregateStats,
                'agents' => $agentBreakdown,
            ],
        ], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }
}
