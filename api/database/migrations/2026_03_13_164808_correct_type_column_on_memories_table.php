<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (DB::getDriverName() === 'pgsql') {
            // Use raw SQL to avoid full column rewrite (Supabase maintenance_work_mem limit)
            DB::statement("ALTER TABLE memories ALTER COLUMN type SET DEFAULT 'note'");
            DB::statement('ALTER TABLE memories ALTER COLUMN type SET NOT NULL');
        }

        Schema::table('memories', function (Blueprint $table) {
            $table->index('type');
        });
    }

    public function down(): void
    {
        Schema::table('memories', function (Blueprint $table) {
            $table->dropIndex(['type']);
            $table->string('type', 255)->default('note')->change();
        });
    }
};
