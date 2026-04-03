<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::table('arena_sessions', function (Blueprint $table) {
            $table->foreignId('match_id')->nullable()->after('challenge_id')->constrained('arena_matches')->nullOnDelete();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('arena_sessions', function (Blueprint $table) {
            $table->dropConstrainedForeignId('match_id');
        });
    }
};
