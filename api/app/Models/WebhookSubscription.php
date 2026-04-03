<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class WebhookSubscription extends Model
{
    use HasFactory, HasUuids;

    protected $fillable = [
        'agent_id',
        'url',
        'events',
        'semantic_query',
        'embedding',
        'secret',
        'is_active',
        'failure_count',
    ];

    protected $hidden = [
        'secret',
        'embedding',
    ];

    protected $attributes = [
        'is_active' => true,
        'failure_count' => 0,
        'events' => '[]',
    ];

    protected $casts = [
        'events' => 'array',
        'is_active' => 'boolean',
    ];

    public function agent()
    {
        return $this->belongsTo(Agent::class);
    }
}
