<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class ArenaSession extends Model
{
    protected $fillable = [
        'agent_id',
        'challenge_id',
        'match_id',
        'status',
        'score',
        'ended_at',
    ];

    protected $casts = [
        'ended_at' => 'datetime',
    ];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }

    public function challenge(): BelongsTo
    {
        return $this->belongsTo(ArenaChallenge::class, 'challenge_id');
    }

    public function match(): BelongsTo
    {
        return $this->belongsTo(ArenaMatch::class, 'match_id');
    }

    public function turns(): HasMany
    {
        return $this->hasMany(ArenaSessionTurn::class, 'session_id');
    }
}
