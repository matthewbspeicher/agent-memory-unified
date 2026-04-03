<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Position;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class TradingPositionController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $query = Position::where('agent_id', $agent->id);

        if ($request->has('paper')) {
            $query->where('paper', filter_var($request->input('paper'), FILTER_VALIDATE_BOOLEAN));
        }

        $positions = $query->orderBy('ticker')->get();

        return response()->json(['data' => $positions], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function show(Request $request, string $ticker): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $paper = filter_var($request->input('paper', 'true'), FILTER_VALIDATE_BOOLEAN);

        $position = Position::where('agent_id', $agent->id)
            ->where('ticker', $ticker)
            ->where('paper', $paper)
            ->firstOrFail();

        return response()->json($position, 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }
}
