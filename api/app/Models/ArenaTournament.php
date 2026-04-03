<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class ArenaTournament extends Model
{
    protected $fillable = [
        'name',
        'type',
        'status',
        'rewards',
        'starts_at',
        'ends_at',
    ];

    protected $casts = [
        'rewards' => 'array',
        'starts_at' => 'datetime',
        'ends_at' => 'datetime',
    ];

    public function participants(): HasMany
    {
        return $this->hasMany(ArenaTournamentParticipant::class, 'tournament_id');
    }

    public function agents()
    {
        return $this->belongsToMany(Agent::class, 'arena_tournament_participants')
            ->withPivot(['rank', 'score', 'status'])
            ->withTimestamps();
    }
}
