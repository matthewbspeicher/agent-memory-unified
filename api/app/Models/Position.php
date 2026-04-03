<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Position extends Model
{
    use HasUuids;

    protected $fillable = [
        'agent_id',
        'ticker',
        'paper',
        'quantity',
        'avg_entry_price',
        'declared_portfolio_value',
        'max_drawdown',
    ];

    protected $casts = [
        'quantity' => 'decimal:8',
        'avg_entry_price' => 'decimal:8',
        'declared_portfolio_value' => 'decimal:8',
        'max_drawdown' => 'decimal:8',
        'paper' => 'boolean',
    ];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }
}
