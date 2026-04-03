<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Str;

class Workspace extends Model
{
    use HasFactory, HasUuids;

    protected $fillable = [
        'name',
        'description',
        'owner_id',
        'is_guild',
        'guild_elo',
    ];

    protected $hidden = [
        'api_token',
        'api_token_hash',
    ];

    protected $casts = [
        'is_guild' => 'boolean',
    ];

    protected $attributes = [
        'is_guild' => false,
        'guild_elo' => 1000,
    ];

    public function owner(): BelongsTo
    {
        return $this->belongsTo(User::class, 'owner_id');
    }

    public function users(): BelongsToMany
    {
        return $this->belongsToMany(User::class, 'workspace_user')
            ->withTimestamps();
    }

    public function agents(): BelongsToMany
    {
        return $this->belongsToMany(Agent::class, 'agent_workspace')
            ->withTimestamps();
    }

    public function memories(): HasMany
    {
        return $this->hasMany(Memory::class);
    }

    public function subscriptions(): HasMany
    {
        return $this->hasMany(WorkspaceSubscription::class);
    }

    public function mentions(): HasMany
    {
        return $this->hasMany(CollaborationMention::class);
    }

    public function tasks(): HasMany
    {
        return $this->hasMany(WorkspaceTask::class);
    }

    public static function generateToken(): string
    {
        return 'wks_'.Str::random(40);
    }

    public function ensureApiToken(): string
    {
        if (! $this->api_token_hash) {
            $token = static::generateToken();
            $this->update(['api_token_hash' => hash('sha256', $token)]);
            return $token;
        }

        throw new \LogicException('Token already exists — cannot retrieve plaintext after creation');
    }
}
