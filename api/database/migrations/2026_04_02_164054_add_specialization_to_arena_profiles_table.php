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
        Schema::table('arena_profiles', function (Blueprint $table) {
            $table->string('specialization')->nullable()->after('level');
            $table->json('skills')->nullable()->after('specialization');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('arena_profiles', function (Blueprint $table) {
            $table->dropColumn(['specialization', 'skills']);
        });
    }
};
