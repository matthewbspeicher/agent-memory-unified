<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ArenaTournamentParticipant extends Model
{
    protected $fillable = [
        'tournament_id',
        'agent_id',
        'rank',
        'score',
        'status',
    ];

    public function tournament(): BelongsTo
    {
        return $this->belongsTo(ArenaTournament::class);
    }

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }
}
