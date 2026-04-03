<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        if (DB::getDriverName() === 'pgsql') {
            DB::statement('ALTER TABLE memories DROP CONSTRAINT IF EXISTS memories_visibility_check');
            DB::statement("ALTER TABLE memories ADD CONSTRAINT memories_visibility_check CHECK (visibility IN ('private', 'shared', 'public', 'workspace', 'archived'))");
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        if (DB::getDriverName() === 'pgsql') {
            DB::statement('ALTER TABLE memories DROP CONSTRAINT IF EXISTS memories_visibility_check');
            DB::statement("ALTER TABLE memories ADD CONSTRAINT memories_visibility_check CHECK (visibility IN ('private', 'shared', 'public', 'workspace'))");
        }
    }
};
