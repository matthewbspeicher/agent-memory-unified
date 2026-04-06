<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Traits\ResolvesAgent;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class AchievementController extends Controller
{
    use ResolvesAgent;

    public function index(Request $request): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        return response()->json($agent->achievements()->orderByDesc('earned_at')->get());
    }
}
