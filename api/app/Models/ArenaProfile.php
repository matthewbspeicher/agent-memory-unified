<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ArenaProfile extends Model
{
    protected $fillable = [
        'agent_id',
        'bio',
        'avatar_url',
        'personality_tags',
        'specialization',
        'skills',
        'xp',
        'level',
        'global_elo',
    ];

    protected $casts = [
        'personality_tags' => 'array',
        'skills' => 'array',
    ];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }
}
