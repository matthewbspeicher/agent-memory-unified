<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;

class Trade extends Model
{
    use HasFactory, HasUuids, SoftDeletes;

    const DIRECTIONS = ['long', 'short'];

    const STATUSES = ['open', 'closed', 'cancelled'];

    protected $fillable = [
        'agent_id',
        'parent_trade_id',
        'ticker',
        'direction',
        'entry_price',
        'exit_price',
        'quantity',
        'fees',
        'entry_at',
        'exit_at',
        'status',
        'pnl',
        'pnl_percent',
        'strategy',
        'confidence',
        'paper',
        'decision_memory_id',
        'outcome_memory_id',
        'metadata',
        'tags',
    ];

    protected $casts = [
        'entry_price' => 'decimal:8',
        'exit_price' => 'decimal:8',
        'quantity' => 'decimal:8',
        'fees' => 'decimal:8',
        'pnl' => 'decimal:8',
        'pnl_percent' => 'decimal:4',
        'confidence' => 'float',
        'paper' => 'boolean',
        'metadata' => 'array',
        'tags' => 'array',
        'entry_at' => 'datetime',
        'exit_at' => 'datetime',
    ];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }

    public function parentTrade(): BelongsTo
    {
        return $this->belongsTo(Trade::class, 'parent_trade_id');
    }

    public function children(): HasMany
    {
        return $this->hasMany(Trade::class, 'parent_trade_id');
    }

    public function decisionMemory(): BelongsTo
    {
        return $this->belongsTo(Memory::class, 'decision_memory_id');
    }

    public function outcomeMemory(): BelongsTo
    {
        return $this->belongsTo(Memory::class, 'outcome_memory_id');
    }

    public function scopeForAgent(Builder $query, Agent $agent): Builder
    {
        return $query->where('agent_id', $agent->id);
    }

    public function scopeOpen(Builder $query): Builder
    {
        return $query->where('status', 'open');
    }

    public function scopeClosed(Builder $query): Builder
    {
        return $query->where('status', 'closed');
    }

    public function scopeParentsOnly(Builder $query): Builder
    {
        return $query->whereNull('parent_trade_id');
    }

    public function scopePaper(Builder $query, bool $paper = true): Builder
    {
        return $query->where('paper', $paper);
    }

    public function oppositeDirection(): string
    {
        return $this->direction === 'long' ? 'short' : 'long';
    }

    public function remainingQuantity(): string
    {
        $childrenQty = $this->children()->sum('quantity');

        return bcsub($this->quantity, $childrenQty, 8);
    }
}
