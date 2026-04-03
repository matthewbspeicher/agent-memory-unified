<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\AppStat;
use App\Models\Memory;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;

class StatsController extends Controller
{
    public function __invoke()
    {
        $stats = Cache::remember('platform:stats', 60, function () {
            $launchDate = Carbon::parse(config('app.launch_date'));

            return [
                'agents_registered' => Agent::count(),
                'memories_stored' => Memory::count(),
                'searches_performed' => AppStat::getStat('searches_performed'),
                'commons_memories' => Memory::where('visibility', 'public')->count(),
                'uptime_days' => max(0, $launchDate->diffInDays(now(), false)),
            ];
        });

        return response()->json($stats);
    }
}
