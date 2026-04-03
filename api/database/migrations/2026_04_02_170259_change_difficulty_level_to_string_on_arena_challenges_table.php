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
        Schema::table('arena_challenges', function (Blueprint $table) {
            $table->string('difficulty_level')->default('easy')->change();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('arena_challenges', function (Blueprint $table) {
            $table->integer('difficulty_level')->default(1)->change();
        });
    }
};
