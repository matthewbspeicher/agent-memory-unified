<?php

namespace App\Http\Controllers;

use App\Models\ArenaGym;
use App\Models\ArenaMatch;
use Inertia\Inertia;

class ArenaController extends Controller
{
    public function index()
    {
        return Inertia::render('Arena', [
            'gyms' => ArenaGym::all(),
            'recentMatches' => collect(),
        ]);
    }

    public function showGym(ArenaGym $gym)
    {
        return Inertia::render('ArenaGym', [
            'gym' => $gym->load('challenges'),
        ]);
    }

    public function showMatch(ArenaMatch $match)
    {
        return Inertia::render('ArenaMatch', [
            'match' => $match->load(['agent1', 'agent2', 'challenge', 'sessions.turns']),
        ]);
    }
}
