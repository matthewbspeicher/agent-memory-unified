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
        Schema::table('arena_matches', function (Blueprint $table) {
            $table->integer('score_1')->default(0)->after('agent_2_id');
            $table->integer('score_2')->default(0)->after('score_1');
            $table->text('judge_feedback')->nullable()->after('winner_id');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('arena_matches', function (Blueprint $table) {
            $table->dropColumn(['score_1', 'score_2', 'judge_feedback']);
        });
    }
};
