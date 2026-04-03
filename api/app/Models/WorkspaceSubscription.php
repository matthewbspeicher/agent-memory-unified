<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class WorkspaceSubscription extends Model
{
    use HasFactory, HasUuids;

    protected $fillable = [
        'workspace_id',
        'agent_id',
        'event_types',
        'callback_url',
        'last_polled_at',
    ];

    protected $casts = [
        'event_types' => 'array',
        'last_polled_at' => 'datetime',
    ];

    public function workspace(): BelongsTo
    {
        return $this->belongsTo(Workspace::class);
    }

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }

    public function matchesEvent(string $eventType): bool
    {
        foreach ($this->event_types as $pattern) {
            if ($pattern === '*' || $pattern === $eventType) {
                return true;
            }
            // Wildcard matching: "memory.*" matches "memory.created"
            if (str_ends_with($pattern, '.*')) {
                $prefix = substr($pattern, 0, -2);
                if (str_starts_with($eventType, $prefix)) {
                    return true;
                }
            }
        }

        return false;
    }

    public function markPolled(): void
    {
        $this->updateQuietly(['last_polled_at' => now()]);
    }
}
