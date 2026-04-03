<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Services\ReplayService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ReplayController extends Controller
{
    public function __construct(
        private ReplayService $replayService,
    ) {}

    public function replay(Request $request): JsonResponse
    {
        $request->validate([
            'paper' => 'nullable',
            'exit_overrides' => 'nullable|array',
            'exit_overrides.*' => 'numeric',
            'exit_offset_pct' => 'nullable|numeric|between:-100,1000',
        ]);

        $agent = $request->attributes->get('agent');
        $paper = filter_var($request->input('paper', false), FILTER_VALIDATE_BOOLEAN);

        $result = $this->replayService->replay(
            $agent,
            $paper,
            $request->input('exit_overrides', []),
            $request->input('exit_offset_pct'),
        );

        return response()->json(['data' => $result], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }
}
