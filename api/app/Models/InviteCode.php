<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Str;

class InviteCode extends Model
{
    use HasUuids;

    protected $fillable = [
        'code_hash',
        'label',
        'created_by_id',
        'used_by_id',
        'used_at',
        'expires_at',
        'max_uses',
        'times_used',
    ];

    protected $casts = [
        'used_at' => 'datetime',
        'expires_at' => 'datetime',
        'max_uses' => 'integer',
        'times_used' => 'integer',
    ];

    public function createdBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by_id');
    }

    public function usedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'used_by_id');
    }

    public function isValid(): bool
    {
        if ($this->expires_at && $this->expires_at->isPast()) {
            return false;
        }

        if ($this->times_used >= $this->max_uses) {
            return false;
        }

        return true;
    }

    public function redeem(User $user): void
    {
        $this->increment('times_used');
        $this->update([
            'used_by_id' => $user->id,
            'used_at' => now(),
        ]);
    }

    public static function generate(
        ?string $label = null,
        ?string $createdById = null,
        int $maxUses = 1,
        ?\DateTimeInterface $expiresAt = null,
    ): array {
        $plainCode = 'inv_' . Str::random(24);

        $invite = self::create([
            'code_hash' => hash('sha256', $plainCode),
            'label' => $label,
            'created_by_id' => $createdById,
            'max_uses' => $maxUses,
            'expires_at' => $expiresAt,
        ]);

        return [$invite, $plainCode];
    }

    public static function findByCode(string $code): ?self
    {
        return self::where('code_hash', hash('sha256', $code))->first();
    }
}
