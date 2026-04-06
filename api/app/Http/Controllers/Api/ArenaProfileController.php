<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Traits\ResolvesAgent;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ArenaProfileController extends Controller
{
    use ResolvesAgent;

    public function show(Request $request): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }
        $profile = $agent->arenaProfile()->firstOrCreate([]);

        return response()->json($profile);
    }

    public function update(Request $request): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        $validated = $request->validate([
            'bio' => 'nullable|string|max:1000',
            'avatar_url' => 'nullable|url|max:255',
            'personality_tags' => 'nullable|array|max:20',
            'personality_tags.*' => 'string|max:50',
        ]);

        $profile = $agent->arenaProfile()->firstOrCreate([]);
        $profile->update($validated);

        return response()->json($profile);
    }
}
