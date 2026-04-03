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
        Schema::table('memories', function (Blueprint $table) {
            // Update the enum check constraint manually for SQLite compatibility (or PostgreSQL check constraint if used)
            $table->foreignUuid('workspace_id')->nullable()->constrained('workspaces')->nullOnDelete()->after('agent_id');
        });

        if (DB::getDriverName() === 'pgsql') {
            // We also need to update the visibility check constraint to allow 'workspace'
            DB::statement('ALTER TABLE memories DROP CONSTRAINT IF EXISTS memories_visibility_check');
            DB::statement("ALTER TABLE memories ADD CONSTRAINT memories_visibility_check CHECK (visibility IN ('private', 'shared', 'public', 'workspace'))");
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('memories', function (Blueprint $table) {
            $table->dropForeign(['workspace_id']);
            $table->dropColumn('workspace_id');
        });

        if (DB::getDriverName() === 'pgsql') {
            DB::statement('ALTER TABLE memories DROP CONSTRAINT IF EXISTS memories_visibility_check');
            DB::statement("ALTER TABLE memories ADD CONSTRAINT memories_visibility_check CHECK (visibility IN ('private', 'shared', 'public'))");
        }
    }
};
