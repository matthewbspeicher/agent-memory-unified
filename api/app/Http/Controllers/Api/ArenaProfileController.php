<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use Illuminate\Http\Request;

class ArenaProfileController extends Controller
{
    public function show(Request $request)
    {
        $agent = $request->attributes->get('agent');
        $profile = $agent->arenaProfile()->firstOrCreate([]);

        return response()->json($profile);
    }

    public function update(Request $request)
    {
        $agent = $request->attributes->get('agent');

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
