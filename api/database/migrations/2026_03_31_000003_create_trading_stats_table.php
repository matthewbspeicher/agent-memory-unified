<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('trading_stats', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('agent_id')->constrained()->cascadeOnDelete();
            $table->boolean('paper')->default(true);
            $table->integer('total_trades')->default(0);
            $table->integer('win_count')->default(0);
            $table->integer('loss_count')->default(0);
            $table->decimal('win_rate', 5, 2)->nullable();
            $table->decimal('profit_factor', 10, 4)->nullable();
            $table->decimal('total_pnl', 24, 8)->default(0);
            $table->decimal('avg_pnl_percent', 8, 4)->nullable();
            $table->decimal('best_trade_pnl', 24, 8)->nullable();
            $table->decimal('worst_trade_pnl', 24, 8)->nullable();
            $table->decimal('sharpe_ratio', 8, 4)->nullable();
            $table->integer('current_streak')->default(0);
            $table->timestamps();

            $table->unique(['agent_id', 'paper']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('trading_stats');
    }
};
