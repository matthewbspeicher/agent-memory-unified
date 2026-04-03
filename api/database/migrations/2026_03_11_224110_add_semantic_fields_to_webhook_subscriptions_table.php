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
        Schema::table('webhook_subscriptions', function (Blueprint $table) {
            $table->text('semantic_query')->nullable()->after('events');
            
            if (\Illuminate\Support\Facades\DB::getDriverName() === 'pgsql') {
                $table->vector('embedding', 1536)->nullable()->after('semantic_query');
            } else {
                $table->text('embedding')->nullable()->after('semantic_query');
            }
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('webhook_subscriptions', function (Blueprint $table) {
            $table->dropColumn(['semantic_query', 'embedding']);
        });
    }
};
