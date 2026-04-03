<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Position;
use App\Services\RiskService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class RiskController extends Controller
{
    public function __construct(
        private RiskService $riskService,
    ) {}

    public function index(Request $request): JsonResponse
    {
        $request->validate([
            'market_prices' => 'nullable|array',
            'market_prices.*' => 'numeric',
            'paper' => 'nullable',
        ]);

        $agent = $request->attributes->get('agent');
        $paper = filter_var($request->input('paper', false), FILTER_VALIDATE_BOOLEAN);
        $marketPrices = $request->input('market_prices', []);

        $positions = Position::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->get();

        $data = $positions->map(fn (Position $p) => $this->riskService->calculatePositionRisk(
            $p,
            $marketPrices[$p->ticker] ?? null,
        ));

        return response()->json(['data' => $data], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function drawdown(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $paper = filter_var($request->input('paper', false), FILTER_VALIDATE_BOOLEAN);

        $result = $this->riskService->calculateMaxDrawdown($agent, $paper);

        return response()->json(['data' => $result], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }
}
