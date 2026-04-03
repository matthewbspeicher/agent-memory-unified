<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Trade;
use App\Services\TradingService;
use Closure;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

class TradingController extends Controller
{
    public function store(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $validated = $request->validate([
            'ticker' => ['required', 'string', 'max:64'],
            'direction' => ['required', Rule::in(Trade::DIRECTIONS)],
            'entry_price' => ['required', 'numeric', 'gt:0'],
            'quantity' => ['required', 'numeric', 'gt:0'],
            'entry_at' => ['required', 'date'],
            'fees' => ['nullable', 'numeric', 'gte:0'],
            'strategy' => ['nullable', 'string', 'max:255'],
            'confidence' => ['nullable', 'numeric', 'between:0,1'],
            'paper' => ['boolean'],
            'parent_trade_id' => [
                'nullable',
                'uuid',
                function (string $attribute, mixed $value, Closure $fail) use ($agent, $request) {
                    if (! $value) {
                        return;
                    }

                    $parent = Trade::where('id', $value)
                        ->where('agent_id', $agent->id)
                        ->first();

                    if (! $parent) {
                        $fail('Parent trade not found or does not belong to this agent.');

                        return;
                    }

                    if ($parent->status !== 'open') {
                        $fail('Parent trade is not open.');

                        return;
                    }

                    if ($request->input('direction') === $parent->direction) {
                        $fail('Exit direction must oppose the parent trade direction.');

                        return;
                    }

                    if ($request->input('ticker') !== $parent->ticker) {
                        $fail('Exit ticker must match parent trade ticker.');

                        return;
                    }

                    if ((bool) $request->input('paper', true) !== $parent->paper) {
                        $fail('Exit paper flag must match parent trade.');

                        return;
                    }

                    $existingChildQty = $parent->children()->sum('quantity');
                    $newQty = $request->input('quantity');
                    $remaining = bcsub($parent->quantity, (string) $existingChildQty, 8);

                    if (bccomp((string) $newQty, $remaining, 8) > 0) {
                        $fail("Exit quantity ({$newQty}) exceeds remaining parent quantity ({$remaining}).");
                    }
                },
            ],
            'decision_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'outcome_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'metadata' => ['nullable', 'array'],
            'tags' => ['nullable', 'array', 'max:20'],
            'tags.*' => ['string', 'max:50'],
        ]);

        $validated['agent_id'] = $agent->id;
        $validated['fees'] = $validated['fees'] ?? 0;
        $validated['paper'] = $validated['paper'] ?? true;

        $trade = Trade::create($validated);

        return response()->json($trade->fresh()->load(['parentTrade', 'children']), 201, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function index(Request $request): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $query = Trade::forAgent($agent)->parentsOnly();

        if ($request->has('ticker')) {
            $query->where('ticker', $request->input('ticker'));
        }
        if ($request->has('status')) {
            $query->where('status', $request->input('status'));
        }
        if ($request->has('direction')) {
            $query->where('direction', $request->input('direction'));
        }
        if ($request->has('strategy')) {
            $query->where('strategy', $request->input('strategy'));
        }
        if ($request->has('paper')) {
            $query->where('paper', filter_var($request->input('paper'), FILTER_VALIDATE_BOOLEAN));
        }
        if ($request->has('from')) {
            $query->where('entry_at', '>=', $request->input('from'));
        }
        if ($request->has('to')) {
            $query->where('entry_at', '<=', $request->input('to'));
        }
        if ($request->has('min_pnl')) {
            $query->where('pnl', '>=', $request->input('min_pnl'));
        }
        if ($request->has('max_pnl')) {
            $query->where('pnl', '<=', $request->input('max_pnl'));
        }
        if ($request->has('tag')) {
            $query->whereJsonContains('tags', $request->input('tag'));
        }
        if ($request->boolean('has_decision_memory')) {
            $query->whereNotNull('decision_memory_id');
        }

        $sort = $request->input('sort', 'entry_at');
        $order = $request->input('order', 'desc');
        $allowedSorts = ['entry_at', 'pnl', 'pnl_percent', 'created_at'];
        if (in_array($sort, $allowedSorts)) {
            $query->orderBy($sort, $order === 'asc' ? 'asc' : 'desc');
        }

        $trades = $query->with(['children', 'decisionMemory', 'outcomeMemory'])
            ->cursorPaginate($request->input('limit', 50));

        return response()->json($trades, 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function show(Request $request, string $id): JsonResponse
    {
        $agent = $request->attributes->get('agent');

        $trade = Trade::forAgent($agent)
            ->with(['children', 'decisionMemory', 'outcomeMemory', 'parentTrade'])
            ->findOrFail($id);

        return response()->json($trade, 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function update(Request $request, string $id): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $trade = Trade::forAgent($agent)->findOrFail($id);

        $immutable = ['ticker', 'direction', 'entry_price', 'quantity', 'fees', 'entry_at', 'parent_trade_id', 'paper'];
        foreach ($immutable as $field) {
            if ($request->has($field)) {
                return response()->json([
                    'message' => "The field '{$field}' is immutable and cannot be changed.",
                    'errors' => [$field => ["The field '{$field}' is immutable."]],
                ], 422);
            }
        }

        $validated = $request->validate([
            'strategy' => ['nullable', 'string', 'max:255'],
            'confidence' => ['nullable', 'numeric', 'between:0,1'],
            'metadata' => ['nullable', 'array'],
            'tags' => ['nullable', 'array', 'max:20'],
            'tags.*' => ['string', 'max:50'],
            'decision_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'outcome_memory_id' => [
                'nullable', 'uuid',
                Rule::exists('memories', 'id')->where('agent_id', $agent->id),
            ],
            'status' => ['nullable', Rule::in(['cancelled'])],
        ]);

        if (isset($validated['status']) && $validated['status'] === 'cancelled' && $trade->status !== 'open') {
            return response()->json([
                'message' => 'Only open trades can be cancelled.',
                'errors' => ['status' => ['Only open trades can be cancelled.']],
            ], 422);
        }

        $trade->update($validated);

        return response()->json($trade->fresh(), 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function destroy(Request $request, string $id): JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $trade = Trade::forAgent($agent)->findOrFail($id);

        if ($trade->status === 'closed') {
            return response()->json([
                'message' => 'Closed trades cannot be deleted.',
                'errors' => ['id' => ['Closed trades cannot be deleted.']],
            ], 422);
        }

        if ($trade->children()->exists()) {
            return response()->json([
                'message' => 'Cannot delete a trade that has child executions.',
                'errors' => ['id' => ['Cannot delete a trade that has child executions.']],
            ], 422);
        }

        $trade->delete();

        // Recalculate position after removing the trade to ensure denormalized state is corrected
        app(TradingService::class)->recalculatePosition(
            $agent,
            $trade->ticker,
            $trade->paper
        );

        return response()->json(['message' => 'Trade deleted.']);
    }
}
