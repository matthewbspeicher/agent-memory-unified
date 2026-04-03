<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

class GraphController extends Controller
{
    public function index(Request $request)
    {
        $user = $request->user();
        $agentIds = $user->agents()->pluck('id');

        $memories = Memory::whereIn('agent_id', $agentIds)
            ->latest()
            ->limit(300)
            ->get();

        return \Inertia\Inertia::render('Graph', [
            'initialData' => $this->buildGraph($memories),
        ]);
    }

    public function me(Request $request)
    {
        $agent = $request->attributes->get('agent');

        return response()->json($this->buildGraph(
            $agent->memories()->latest()->limit(200)->get()
        ));
    }

    public function show(string $agentId)
    {
        $agent = Agent::findOrFail($agentId);

        $graph = $this->buildGraph(
            $agent->memories()->where('visibility', 'public')->latest()->limit(200)->get()
        );

        $graph['agent'] = [
            'id' => $agent->id,
            'name' => $agent->name,
        ];

        return response()->json($graph);
    }

    private function buildGraph($memories): array
    {
        $memoryIds = $memories->pluck('id');

        $nodes = $memories->map(fn (Memory $m) => [
            'id' => $m->id,
            'key' => $m->key,
            'summary' => $m->summary ?? Str::limit($m->value, 100),
            'type' => $m->type,
            'category' => $m->category,
            'importance' => $m->importance,
            'created_at' => $m->created_at->toIso8601String(),
        ])->values();

        $edges = DB::table('memory_relations')
            ->where(function ($q) use ($memoryIds) {
                $q->whereIn('source_id', $memoryIds)
                    ->whereIn('target_id', $memoryIds);
            })
            ->select('source_id as source', 'target_id as target', 'type as relation')
            ->distinct()
            ->get()
            ->values();

        return ['nodes' => $nodes, 'edges' => $edges];
    }
}
