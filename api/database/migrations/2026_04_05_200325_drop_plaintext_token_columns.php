<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     *
     * Security hardening: Drop plaintext token columns after confirming
     * all code uses hash-only lookups (completed in S1.2+S2+S3+S4).
     *
     * Task S1.3: Drop plaintext token columns
     */
    public function up(): void
    {
        Schema::table('agents', function (Blueprint $table) {
            $table->dropColumn('api_token');
        });

        Schema::table('users', function (Blueprint $table) {
            $table->dropColumn(['api_token', 'magic_link_token']);
        });

        Schema::table('workspaces', function (Blueprint $table) {
            $table->dropColumn('api_token');
        });
    }

    /**
     * Reverse the migrations.
     *
     * Note: This will recreate the columns but data is lost.
     * Only for emergency rollback during initial deployment.
     */
    public function down(): void
    {
        Schema::table('agents', function (Blueprint $table) {
            $table->string('api_token', 80)->nullable()->unique();
        });

        Schema::table('users', function (Blueprint $table) {
            $table->string('api_token', 80)->nullable()->unique();
            $table->string('magic_link_token', 80)->nullable()->unique();
        });

        Schema::table('workspaces', function (Blueprint $table) {
            $table->string('api_token', 80)->nullable()->unique();
        });
    }
};
