<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class TradingStats extends Model
{
    use HasUuids;

    protected $fillable = [
        'agent_id',
        'paper',
        'total_trades',
        'win_count',
        'loss_count',
        'win_rate',
        'profit_factor',
        'total_pnl',
        'avg_pnl_percent',
        'best_trade_pnl',
        'worst_trade_pnl',
        'sharpe_ratio',
        'current_streak',
    ];

    protected $casts = [
        'paper' => 'boolean',
        'win_rate' => 'decimal:2',
        'profit_factor' => 'decimal:4',
        'total_pnl' => 'decimal:8',
        'avg_pnl_percent' => 'decimal:4',
        'best_trade_pnl' => 'decimal:8',
        'worst_trade_pnl' => 'decimal:8',
        'sharpe_ratio' => 'decimal:4',
    ];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }
}
