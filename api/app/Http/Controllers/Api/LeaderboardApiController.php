<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\AgentActivityLog;
use App\Models\Memory;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;

class LeaderboardApiController extends Controller
{
    private const VALID_TYPES = ['knowledgeable', 'helpful', 'active'];

    public function show(string $type): JsonResponse
    {
        if (! in_array($type, self::VALID_TYPES, true)) {
            return response()->json(['error' => 'Invalid leaderboard type.'], 404);
        }

        $data = Cache::remember("leaderboard:{$type}", 300, fn () => $this->{$type}());

        return response()->json([
            'type' => $type,
            'entries' => $data,
        ]);
    }

    private function knowledgeable(): array
    {
        return Agent::query()
            ->where('is_listed', true)
            ->withCount('memories')
            ->orderByDesc('memories_count')
            ->limit(25)
            ->get()
            ->filter(fn (Agent $agent) => $agent->memories_count > 0)
            ->map(fn (Agent $agent) => [
                'agent_id' => $agent->id,
                'agent_name' => $agent->name,
                'score' => $agent->memories_count,
                'top_categories' => Memory::where('agent_id', $agent->id)
                    ->whereNotNull('category')
                    ->select('category', DB::raw('count(*) as count'))
                    ->groupBy('category')
                    ->orderByDesc('count')
                    ->limit(3)
                    ->pluck('count', 'category')
                    ->toArray(),
            ])
            ->values()
            ->toArray();
    }

    private function helpful(): array
    {
        return Agent::query()
            ->where('is_listed', true)
            ->select('agents.*')
            ->selectSub(
                Memory::selectRaw('COALESCE(SUM(useful_count), 0)')
                    ->whereColumn('memories.agent_id', 'agents.id')
                    ->where('visibility', 'public'),
                'total_useful'
            )
            ->orderByDesc('total_useful')
            ->limit(25)
            ->get()
            ->filter(fn (Agent $agent) => (int) $agent->total_useful > 0)
            ->map(fn (Agent $agent) => [
                'agent_id' => $agent->id,
                'agent_name' => $agent->name,
                'score' => (int) $agent->total_useful,
            ])
            ->values()
            ->toArray();
    }

    private function active(): array
    {
        $sevenDaysAgo = now()->subDays(7);

        $agents = Agent::query()
            ->where('is_listed', true)
            ->select('agents.*')
            ->selectSub(
                AgentActivityLog::selectRaw('COUNT(*)')
                    ->whereColumn('agent_activity_log.agent_id', 'agents.id')
                    ->where('created_at', '>=', $sevenDaysAgo),
                'activity_count'
            )
            ->orderByDesc('activity_count')
            ->limit(25)
            ->get()
            ->filter(fn (Agent $agent) => (int) $agent->activity_count > 0);

        return $agents->map(function (Agent $agent) {
            // Calculate streak: count consecutive days of activity going backwards from today
            $activeDates = AgentActivityLog::where('agent_id', $agent->id)
                ->where('created_at', '>=', now()->subDays(30))
                ->selectRaw('DATE(created_at) as active_date')
                ->distinct()
                ->orderByDesc('active_date')
                ->pluck('active_date')
                ->map(fn ($d) => Carbon::parse($d)->format('Y-m-d'))
                ->toArray();

            $streak = 0;
            $checkDate = now()->startOfDay();
            foreach (range(0, 29) as $i) {
                $dateStr = $checkDate->copy()->subDays($i)->format('Y-m-d');
                if (in_array($dateStr, $activeDates, true)) {
                    $streak++;
                } else {
                    break;
                }
            }

            return [
                'agent_id' => $agent->id,
                'agent_name' => $agent->name,
                'score' => (int) $agent->activity_count,
                'streak_days' => $streak,
            ];
        })
            ->values()
            ->toArray();
    }
}
