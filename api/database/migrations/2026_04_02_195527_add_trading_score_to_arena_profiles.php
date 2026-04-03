<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::table('arena_profiles', function (Blueprint $table) {
            $table->decimal('trading_score', 8, 2)->nullable()->after('global_elo');
        });

        // Data migration: move personality_tags['trading_score'] to column (PostgreSQL only)
        if (DB::connection()->getDriverName() === 'pgsql') {
            DB::statement("
                UPDATE arena_profiles
                SET trading_score = CAST(personality_tags->>'trading_score' AS DECIMAL)
                WHERE personality_tags ? 'trading_score'
            ");

            // Remove key from JSON
            DB::statement("
                UPDATE arena_profiles
                SET personality_tags = personality_tags - 'trading_score'
                WHERE personality_tags ? 'trading_score'
            ");
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('arena_profiles', function (Blueprint $table) {
            $table->dropColumn('trading_score');
        });
    }
};
