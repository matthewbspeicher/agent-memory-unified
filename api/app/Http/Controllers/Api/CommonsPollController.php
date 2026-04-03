<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Memory;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;

class CommonsPollController extends Controller
{
    public function __invoke(Request $request): JsonResponse
    {
        $since = $request->query('since');

        $query = Memory::query()
            ->where('visibility', 'public')
            ->with('agent:id,name,description')
            ->orderBy('created_at', 'asc')
            ->limit(50);

        if ($since) {
            $query->where('created_at', '>', Carbon::parse($since));
        } else {
            $query->latest()->limit(50)->reorder()->orderBy('created_at', 'asc');
        }

        $memories = $query->get();

        $total = cache()->remember('commons:total_memories', 30, function () {
            return Memory::where('visibility', 'public')->count();
        });

        return response()->json([
            'memories' => $memories->map(fn ($m) => [
                'id' => $m->id,
                'key' => $m->key,
                'value' => $m->value,
                'visibility' => $m->visibility,
                'metadata' => $m->metadata,
                'created_at' => $m->created_at->toIso8601String(),
                'agent' => [
                    'id' => $m->agent->id,
                    'name' => $m->agent->name,
                    'description' => $m->agent->description,
                ],
            ]),
            'total_memories' => $total,
            'server_time' => now()->toIso8601String(),
        ]);
    }
}
