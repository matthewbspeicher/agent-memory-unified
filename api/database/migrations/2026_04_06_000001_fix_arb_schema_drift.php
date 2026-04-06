<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (Schema::hasTable('arb_spread_observations')) {
            Schema::table('arb_spread_observations', function (Blueprint $table) {
                if (!Schema::hasColumn('arb_spread_observations', 'is_claimed')) {
                    $table->boolean('is_claimed')->default(false);
                }
                if (!Schema::hasColumn('arb_spread_observations', 'claimed_at')) {
                    $table->timestamp('claimed_at')->nullable();
                }
                if (!Schema::hasColumn('arb_spread_observations', 'claimed_by')) {
                    $table->string('claimed_by')->nullable();
                }
            });
        }

        if (Schema::hasTable('arb_trades')) {
            Schema::table('arb_trades', function (Blueprint $table) {
                if (!Schema::hasColumn('arb_trades', 'sequencing')) {
                    $table->string('sequencing')->nullable();
                }
            });
        }
    }

    public function down(): void
    {
        if (Schema::hasTable('arb_spread_observations')) {
            Schema::table('arb_spread_observations', function (Blueprint $table) {
                $table->dropColumn(['is_claimed', 'claimed_at', 'claimed_by']);
            });
        }

        if (Schema::hasTable('arb_trades')) {
            Schema::table('arb_trades', function (Blueprint $table) {
                $table->dropColumn('sequencing');
            });
        }
    }
};
