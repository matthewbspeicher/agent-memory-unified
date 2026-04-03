<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Trade;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Symfony\Component\HttpFoundation\Response;

class TradeExportController extends Controller
{
    public function export(Request $request): JsonResponse|Response
    {
        $request->validate([
            'format' => 'nullable|string|in:json,csv',
            'paper' => 'nullable',
            'from' => 'nullable|date',
            'to' => 'nullable|date',
            'status' => 'nullable|string|in:open,closed,cancelled',
            'ticker' => 'nullable|string|max:64',
        ]);

        $agent = $request->attributes->get('agent');
        $paper = filter_var($request->input('paper', false), FILTER_VALIDATE_BOOLEAN);
        $format = $request->input('format', 'json');

        $query = Trade::where('agent_id', $agent->id)
            ->where('paper', $paper)
            ->whereNull('parent_trade_id')
            ->orderBy('entry_at');

        if ($request->has('from')) {
            $query->where('entry_at', '>=', $this->normalizeDateBoundary($request->input('from')));
        }
        if ($request->has('to')) {
            $query->where('entry_at', '<=', $this->normalizeDateBoundary($request->input('to'), true));
        }
        if ($request->has('status')) {
            $query->where('status', $request->input('status'));
        }
        if ($request->has('ticker')) {
            $query->where('ticker', $request->input('ticker'));
        }

        $columns = [
            'id', 'ticker', 'direction', 'entry_price', 'exit_price',
            'quantity', 'fees', 'pnl', 'pnl_percent', 'strategy', 'tags',
            'entry_at', 'exit_at', 'status', 'confidence', 'paper',
        ];

        if ($format === 'csv') {
            return $this->csvResponse($query, $columns);
        }

        $trades = $query->get($columns)->map(fn (Trade $trade) => $this->normalizeTrade($trade));

        return response()->json(['data' => $trades], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    private function csvResponse($query, array $columns): Response
    {
        $headers = [
            'Content-Type' => 'text/csv; charset=UTF-8',
            'Content-Disposition' => 'attachment; filename="trades-export-'.now()->format('Y-m-d').'.csv"',
        ];

        $handle = fopen('php://temp', 'r+');
        fputcsv($handle, $columns);

        $query->chunk(500, function ($trades) use ($handle, $columns) {
            foreach ($trades as $trade) {
                $row = [];
                foreach ($columns as $col) {
                    $val = $trade->{$col};
                    if ($val instanceof \DateTimeInterface) {
                        $val = $val->toIso8601String();
                    } elseif (is_array($val)) {
                        $val = implode(';', $val);
                    }
                    $row[] = $val;
                }
                fputcsv($handle, $row);
            }
        });

        rewind($handle);
        $csv = stream_get_contents($handle) ?: '';
        fclose($handle);

        return response($csv, 200, $headers);
    }

    private function normalizeTrade(Trade $trade): array
    {
        return [
            'id' => $trade->id,
            'ticker' => $trade->ticker,
            'direction' => $trade->direction,
            'entry_price' => $trade->entry_price === null ? null : (float) $trade->entry_price,
            'exit_price' => $trade->exit_price === null ? null : (float) $trade->exit_price,
            'quantity' => $trade->quantity === null ? null : (float) $trade->quantity,
            'fees' => $trade->fees === null ? null : (float) $trade->fees,
            'pnl' => $trade->pnl === null ? null : (float) $trade->pnl,
            'pnl_percent' => $trade->pnl_percent === null ? null : (float) $trade->pnl_percent,
            'strategy' => $trade->strategy,
            'tags' => $trade->tags,
            'entry_at' => $trade->entry_at?->toIso8601String(),
            'exit_at' => $trade->exit_at?->toIso8601String(),
            'status' => $trade->status,
            'confidence' => $trade->confidence === null ? null : (float) $trade->confidence,
            'paper' => (bool) $trade->paper,
        ];
    }

    private function normalizeDateBoundary(?string $value, bool $isEnd = false): ?Carbon
    {
        if ($value === null) {
            return null;
        }

        $date = Carbon::parse($value);

        if (preg_match('/^\d{4}-\d{2}-\d{2}$/', $value) === 1) {
            return $isEnd ? $date->endOfDay() : $date->startOfDay();
        }

        return $date;
    }
}
