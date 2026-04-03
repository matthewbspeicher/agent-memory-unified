<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('trades', function (Blueprint $table) {
            $table->json('tags')->nullable()->after('metadata');
        });

        if (DB::getDriverName() === 'pgsql') {
            DB::statement('CREATE INDEX trades_tags_gin ON trades USING GIN (tags jsonb_path_ops)');
        }
    }

    public function down(): void
    {
        Schema::table('trades', function (Blueprint $table) {
            $table->dropColumn('tags');
        });
    }
};
