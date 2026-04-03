<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\Trade;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class SignalController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $broadcasterIds = Agent::where('broadcasts_signals', true)
            ->where('is_listed', true)
            ->pluck('id');

        $query = Trade::whereIn('agent_id', $broadcasterIds)
            ->where('paper', false)
            ->whereNull('parent_trade_id')
            ->with('agent:id,name')
            ->orderByDesc('created_at');

        if ($request->has('ticker')) {
            $query->where('ticker', $request->input('ticker'));
        }

        if ($request->has('direction')) {
            $query->where('direction', $request->input('direction'));
        }

        if ($request->has('status')) {
            $query->where('status', $request->input('status'));
        }

        $trades = $query->cursorPaginate($request->input('limit', 50));

        $data = collect($trades->items())->map(fn (Trade $t) => [
            'trade_id' => $t->id,
            'agent_id' => $t->agent_id,
            'agent_name' => $t->agent?->name,
            'ticker' => $t->ticker,
            'direction' => $t->direction,
            'entry_price' => $t->entry_price,
            'exit_price' => $t->exit_price,
            'quantity' => $t->quantity,
            'pnl' => $t->pnl,
            'pnl_percent' => $t->pnl_percent,
            'status' => $t->status,
            'strategy' => $t->strategy,
            'tags' => $t->tags,
            'entry_at' => $t->entry_at?->toIso8601String(),
            'exit_at' => $t->exit_at?->toIso8601String(),
            'created_at' => $t->created_at->toIso8601String(),
        ]);

        return response()->json([
            'data' => $data,
            'next_cursor' => $trades->nextCursor()?->encode(),
        ]);
    }
}
