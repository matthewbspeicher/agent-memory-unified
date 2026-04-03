<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class TradeAlert extends Model
{
    use HasFactory, HasUuids;

    public const CONDITIONS = [
        'pnl_above',
        'pnl_below',
        'trade_opened',
        'trade_closed',
    ];

    protected $fillable = [
        'agent_id',
        'ticker',
        'condition',
        'threshold',
        'delivery',
        'is_active',
        'trigger_count',
        'last_triggered_at',
    ];

    protected $casts = [
        'threshold' => 'decimal:8',
        'is_active' => 'boolean',
        'last_triggered_at' => 'datetime',
    ];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }
}
