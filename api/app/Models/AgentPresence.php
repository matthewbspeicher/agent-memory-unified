<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class AgentPresence extends Model
{
    use HasFactory, HasUuids;

    protected $fillable = [
        'workspace_id',
        'agent_id',
        'status',
        'metadata',
        'last_seen_at',
    ];

    protected $casts = [
        'metadata' => 'array',
        'last_seen_at' => 'datetime',
    ];

    public const STATUS_ONLINE = 'online';

    public const STATUS_AWAY = 'away';

    public const STATUS_BUSY = 'busy';

    public const STATUS_OFFLINE = 'offline';

    public const STALE_THRESHOLD_MINUTES = 5;

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }

    public function workspace(): BelongsTo
    {
        return $this->belongsTo(Workspace::class);
    }

    public function scopeOnline(Builder $query): Builder
    {
        return $query->where('status', self::STATUS_ONLINE);
    }

    public function scopeAway(Builder $query): Builder
    {
        return $query->where('status', self::STATUS_AWAY);
    }

    public function scopeBusy(Builder $query): Builder
    {
        return $query->where('status', self::STATUS_BUSY);
    }

    public function scopeStale(Builder $query): Builder
    {
        return $query->where('last_seen_at', '<', now()->subMinutes(self::STALE_THRESHOLD_MINUTES));
    }

    public function scopeActive(Builder $query): Builder
    {
        return $query->where(function ($q) {
            $q->where('status', '!=', self::STATUS_OFFLINE)
                ->orWhere('last_seen_at', '>', now()->subMinutes(self::STALE_THRESHOLD_MINUTES));
        });
    }

    public function isOnline(): bool
    {
        return $this->status === self::STATUS_ONLINE;
    }

    public function isStale(): bool
    {
        return $this->last_seen_at !== null
            && $this->last_seen_at->lt(now()->subMinutes(self::STALE_THRESHOLD_MINUTES));
    }

    public function refreshHeartbeat(string $status = self::STATUS_ONLINE, ?array $metadata = null): self
    {
        $this->status = $status;
        $this->last_seen_at = now();

        if ($metadata !== null) {
            $this->metadata = array_merge($this->metadata ?? [], $metadata);
        }

        $this->save();

        return $this;
    }
}
