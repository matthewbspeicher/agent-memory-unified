<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('arena_profiles', function (Blueprint $table) {
            $table->integer('xp')->default(0)->after('global_elo');
            $table->integer('level')->default(1)->after('xp');
        });
    }

    public function down(): void
    {
        Schema::table('arena_profiles', function (Blueprint $table) {
            $table->dropColumn(['xp', 'level']);
        });
    }
};
