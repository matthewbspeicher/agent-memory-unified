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
        Schema::table('arena_gyms', function (Blueprint $table) {
            $table->string('type')->default('chat')->after('is_official');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('arena_gyms', function (Blueprint $table) {
            $table->dropColumn('type');
        });
    }
};
