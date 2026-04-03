<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use Illuminate\Http\Request;

class AchievementController extends Controller
{
    public function index(Request $request)
    {
        $agent = $request->attributes->get('agent');

        return response()->json($agent->achievements()->orderByDesc('earned_at')->get());
    }
}
