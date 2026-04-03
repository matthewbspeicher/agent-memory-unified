<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\TradeAlert;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

class TradeAlertController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $alerts = TradeAlert::where('agent_id', $agent->id)
            ->orderByDesc('created_at')
            ->get();

        return response()->json(['data' => $alerts->map(fn (TradeAlert $alert) => $alert->toArray())->values()], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function store(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $count = TradeAlert::where('agent_id', $agent->id)->count();
        if ($count >= 25) {
            return response()->json(['message' => 'Maximum 25 alerts per agent.'], 422);
        }

        $validated = $request->validate([
            'ticker' => 'nullable|string|max:64',
            'condition' => ['required', Rule::in(TradeAlert::CONDITIONS)],
            'threshold' => 'nullable|required_if:condition,pnl_above|required_if:condition,pnl_below|numeric',
            'delivery' => 'nullable|string|in:webhook,poll',
        ]);

        $alert = TradeAlert::create([
            'agent_id' => $agent->id,
            ...$validated,
        ]);

        return response()->json(['data' => $alert->fresh()->toArray()], 201, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function destroy(Request $request, string $id): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $alert = TradeAlert::where('agent_id', $agent->id)->findOrFail($id);
        $alert->delete();

        return response()->json(null, 204);
    }
}
