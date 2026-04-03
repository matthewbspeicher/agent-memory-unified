<?php

namespace App\Models;

use Illuminate\Auth\Authenticatable;
use Illuminate\Contracts\Auth\Authenticatable as AuthenticatableContract;
use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\HasOne;
use Illuminate\Support\Str;

class Agent extends Model implements AuthenticatableContract
{
    use Authenticatable, HasFactory, HasUuids;

    protected $fillable = [
        'owner_id',
        'name',
        'description',
        'is_listed',
        'broadcasts_signals',
        'last_seen_at', // Keep for touchLastSeen()
    ];

    protected $hidden = [
        'api_token',
        'token_hash',
    ];

    protected $casts = [
        'is_active' => 'boolean',
        'is_listed' => 'boolean',
        'broadcasts_signals' => 'boolean',
        'last_seen_at' => 'datetime',
        'scopes' => 'array',
    ];

    /**
     * Default scopes for new agents.
     */
    const DEFAULT_SCOPES = [
        'memory:read',
        'memory:write',
        'arena:compete',
        'profile:read',
    ];

    /**
     * Check if the agent has a specific permission scope.
     */
    public function hasScope(string $scope): bool
    {
        return in_array($scope, $this->scopes ?? []);
    }

    public static function generateToken(): string
    {
        return 'amc_'.Str::random(60);
    }

    public static function hashToken(string $token): string
    {
        return hash('sha256', $token);
    }

    public function owner(): BelongsTo
    {
        return $this->belongsTo(User::class, 'owner_id');
    }

    public function memories(): HasMany
    {
        return $this->hasMany(Memory::class);
    }

    public function achievements(): HasMany
    {
        return $this->hasMany(Achievement::class);
    }

    public function workspaces(): BelongsToMany
    {
        return $this->belongsToMany(Workspace::class, 'agent_workspace')
            ->withTimestamps();
    }

    public function arenaProfile(): HasOne
    {
        return $this->hasOne(ArenaProfile::class);
    }

    public function ownedGyms(): HasMany
    {
        return $this->hasMany(ArenaGym::class, 'agent_id');
    }

    public function arenaSessions(): HasMany
    {
        return $this->hasMany(ArenaSession::class);
    }

    public function matchesAsAgent1(): HasMany
    {
        return $this->hasMany(ArenaMatch::class, 'agent_1_id');
    }

    public function matchesAsAgent2(): HasMany
    {
        return $this->hasMany(ArenaMatch::class, 'agent_2_id');
    }

    public function wonMatches(): HasMany
    {
        return $this->hasMany(ArenaMatch::class, 'winner_id');
    }

    public function arenaTournaments(): BelongsToMany
    {
        return $this->belongsToMany(ArenaTournament::class, 'arena_tournament_participants')
            ->withPivot(['rank', 'score', 'status'])
            ->withTimestamps();
    }

    public function trades(): HasMany
    {
        return $this->hasMany(Trade::class);
    }

    public function positions(): HasMany
    {
        return $this->hasMany(Position::class);
    }

    public function tradingStats(): HasMany
    {
        return $this->hasMany(TradingStats::class);
    }

    public function webhooks(): HasMany
    {
        return $this->hasMany(WebhookSubscription::class);
    }

    public function touchLastSeen(): void
    {
        $this->updateQuietly(['last_seen_at' => now()]);
    }
}
