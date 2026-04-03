<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class ArenaGym extends Model
{
    use HasFactory;

    protected $fillable = [
        'owner_id',
        'agent_id',
        'name',
        'description',
        'icon_url',
        'is_official',
        'type',
    ];

    protected $casts = [
        'is_official' => 'boolean',
    ];

    public function owner(): BelongsTo
    {
        return $this->belongsTo(User::class, 'owner_id');
    }

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }

    public function challenges(): HasMany
    {
        return $this->hasMany(ArenaChallenge::class, 'gym_id');
    }
}
