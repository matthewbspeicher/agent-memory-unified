<?php

namespace App\Models;

use Database\Factories\UserFactory;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Foundation\Auth\User as Authenticatable;
use Illuminate\Notifications\Notifiable;
use Illuminate\Support\Str;

class User extends Authenticatable
{
    /** @use HasFactory<UserFactory> */
    use HasFactory, Notifiable;

    protected $fillable = [
        'name',
        'email',
        'password',
        'api_token',
        'api_token_hash',
        'magic_link_token',
        'magic_link_token_hash',
        'magic_link_expires_at',
    ];

    protected $hidden = [
        'password',
        'remember_token',
        'api_token',
        'api_token_hash',
        'magic_link_token',
        'magic_link_token_hash',
    ];

    protected function casts(): array
    {
        return [
            'email_verified_at' => 'datetime',
            'password' => 'hashed',
            'magic_link_expires_at' => 'datetime',
        ];
    }

    // -------------------------------------------------------------------------
    // Relationships
    // -------------------------------------------------------------------------

    public function agents(): HasMany
    {
        return $this->hasMany(Agent::class, 'owner_id');
    }

    public function sharedWorkspaces(): BelongsToMany
    {
        return $this->belongsToMany(Workspace::class, 'workspace_user')
            ->withTimestamps();
    }

    public function ownedGyms(): HasMany
    {
        return $this->hasMany(ArenaGym::class, 'owner_id');
    }

    public function ownedWorkspaces(): HasMany
    {
        return $this->hasMany(Workspace::class, 'owner_id');
    }

    // -------------------------------------------------------------------------
    // Plan helpers (Simplified for internal use)
    // -------------------------------------------------------------------------

    public function isPro(): bool
    {
        return true;
    }

    public function hasUnlimitedAgentAccess(): bool
    {
        return true;
    }

    public function maxAgents(): int
    {
        return PHP_INT_MAX;
    }

    public function maxMemoriesPerAgent(): int
    {
        return 100_000;
    }

    public function canCreateWorkspace(): bool
    {
        return true;
    }

    public function isDowngraded(): bool
    {
        return false;
    }

    public function isOnGracePeriod(): bool
    {
        return false;
    }

    public function hasPaymentFailure(): bool
    {
        return false;
    }

    // -------------------------------------------------------------------------
    // Auth helpers
    // -------------------------------------------------------------------------

    public function generateMagicLink(): string
    {
        $token = Str::random(64);

        $this->update([
            'magic_link_token' => $token,
            'magic_link_token_hash' => hash('sha256', $token),
            'magic_link_expires_at' => now()->addMinutes(30),
        ]);

        return $token;
    }

    public function hasValidMagicLink(string $token): bool
    {
        return hash_equals($this->magic_link_token ?? '', $token)
            && $this->magic_link_expires_at
            && $this->magic_link_expires_at->isFuture();
    }

    public function clearMagicLink(): void
    {
        $this->update([
            'magic_link_token' => null,
            'magic_link_expires_at' => null,
        ]);
    }

    public static function generateToken(): string
    {
        return 'own_'.Str::random(40);
    }

    public function ensureApiToken(): string
    {
        if (! $this->api_token) {
            $token = self::generateToken();
            $this->update([
                'api_token' => $token,
                'api_token_hash' => hash('sha256', $token),
            ]);
        }

        return $this->api_token;
    }
}
