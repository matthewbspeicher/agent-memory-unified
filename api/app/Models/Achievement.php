<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Achievement extends Model
{
    public $timestamps = false;

    protected $fillable = ['agent_id', 'achievement_slug', 'earned_at'];

    protected $casts = ['earned_at' => 'datetime'];

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }
}
