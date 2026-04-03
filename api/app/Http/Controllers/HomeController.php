<?php

namespace App\Http\Controllers;

use App\Models\Agent;
use App\Models\Memory;
use Inertia\Inertia;

class HomeController extends Controller
{
    public function __invoke()
    {
        try {
            $stats = cache()->remember('home:stats', 60, function () {
                return [
                    'totalMemories' => Memory::count(),
                    'totalAgents' => Agent::whereRaw('"is_active" IS TRUE')->count(),
                ];
            });

            $recentPublic = cache()->remember('home:recent_public', 30, function () {
                return Memory::with('agent:id,name')
                    ->where('visibility', 'public')
                    ->latest()
                    ->limit(5)
                    ->get(['id', 'agent_id', 'key', 'value', 'created_at']);
            });
        } catch (\Throwable $e) {
            $stats = ['totalMemories' => 0, 'totalAgents' => 0];
            $recentPublic = collect();
        }

        return Inertia::render('Home', [
            'totalMemories' => $stats['totalMemories'],
            'totalAgents' => $stats['totalAgents'],
            'recentPublic' => $recentPublic,
        ]);
    }
}
