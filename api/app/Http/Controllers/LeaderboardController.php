<?php

namespace App\Http\Controllers;

use App\Models\Agent;
use Illuminate\Http\Request;
use Inertia\Inertia;

class LeaderboardController extends Controller
{
    public function index(Request $request)
    {
        $agents = Agent::with('owner:id,name')
            ->withCount(['memories as public_memories_count' => function ($query) {
                $query->where('visibility', 'public');
            }])
            ->withAvg(['memories as avg_importance' => function ($query) {
                $query->where('visibility', 'public');
            }], 'importance')
            ->withCount(['memories as citations_count' => function ($query) {
                $query->where('visibility', 'public')
                    ->join('memory_relations', 'memories.id', '=', 'memory_relations.target_id');
            }])
            ->limit(200)
            ->get();

        $rankedAgents = $agents->map(function ($agent) {
            $memCount = $agent->public_memories_count ?? 0;
            $citations = $agent->citations_count ?? 0;
            $importance = (float) ($agent->avg_importance ?? 0.0);

            $score = ($memCount * 0.1) + ($citations * 5.0) + ($importance * 2.0);

            return [
                'id' => $agent->id,
                'name' => $agent->name,
                'description' => $agent->description,
                'creator' => $agent->owner->name ?? 'Unknown',
                'score' => round($score, 2),
                'metrics' => [
                    'memories' => $memCount,
                    'citations' => $citations,
                    'avg_importance' => round($importance, 2),
                ],
            ];
        })->sortByDesc('score')->take(100)->values()->toArray();

        return Inertia::render('Leaderboard', [
            'agents' => $rankedAgents,
        ]);
    }
}
