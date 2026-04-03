<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ArenaSessionTurn extends Model
{
    protected $fillable = [
        'session_id',
        'turn_number',
        'agent_payload',
        'validator_response',
    ];

    protected $casts = [
        'agent_payload' => 'array',
        'validator_response' => 'array',
    ];

    public function session(): BelongsTo
    {
        return $this->belongsTo(ArenaSession::class, 'session_id');
    }
}
