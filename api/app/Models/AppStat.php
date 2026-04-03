<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Facades\DB;

class AppStat extends Model
{
    public $timestamps = false;

    public $incrementing = false;

    protected $primaryKey = 'key';

    protected $keyType = 'string';

    protected $fillable = ['key', 'value', 'updated_at'];

    public static function incrementStat(string $key): void
    {
        try {
            DB::transaction(function () use ($key) {
                DB::statement(
                    'INSERT INTO app_stats (key, value, updated_at) VALUES (?, 1, now())
                     ON CONFLICT (key) DO UPDATE SET value = app_stats.value + 1, updated_at = now()',
                    [$key]
                );
            });
        } catch (\Throwable) {
            // Stat tracking is best-effort; never block the main request
        }
    }

    public static function getStat(string $key): int
    {
        return (int) (static::where('key', $key)->value('value') ?? 0);
    }
}
