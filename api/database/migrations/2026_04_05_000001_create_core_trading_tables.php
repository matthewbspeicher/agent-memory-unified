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
        // Opportunities
        Schema::create('opportunities', function (Blueprint $table) {
            $table->string('id')->primary();
            $table->string('agent_name');
            $table->string('symbol');
            $table->string('signal');
            $table->decimal('confidence', 8, 4);
            $table->text('reasoning');
            $table->text('suggested_trade')->nullable();
            $table->string('status')->default('pending')->index();
            $table->timestamp('expires_at')->nullable();
            $table->jsonb('data')->nullable();
            $table->timestamps();

            $table->index(['agent_name', 'created_at']);
            $table->index(['symbol', 'created_at']);
        });

        // Trade Executions (opportunity-linked, distinct from AMC paper trades table)
        Schema::create('trade_executions', function (Blueprint $table) {
            $table->id();
            $table->string('opportunity_id')->nullable();
            $table->string('agent_name')->nullable();
            $table->jsonb('order_result');
            $table->jsonb('risk_evaluation')->nullable();
            $table->timestamps();

            $table->foreign('opportunity_id')->references('id')->on('opportunities')->onDelete('set null');
            $table->index(['opportunity_id', 'created_at']);
            $table->index(['agent_name', 'created_at']);
        });

        // Tracked Positions
        Schema::create('tracked_positions', function (Blueprint $table) {
            $table->id();
            $table->string('agent_name');
            $table->string('opportunity_id');
            $table->string('symbol');
            $table->string('side');
            $table->decimal('entry_price', 20, 8);
            $table->integer('entry_quantity');
            $table->decimal('entry_fees', 20, 8)->default(0);
            $table->timestamp('entry_time');
            $table->decimal('exit_price', 20, 8)->nullable();
            $table->decimal('exit_fees', 20, 8)->nullable();
            $table->timestamp('exit_time')->nullable();
            $table->string('exit_reason')->nullable();
            $table->decimal('max_adverse_excursion', 20, 8)->default(0);
            $table->string('status')->default('open')->index();
            $table->timestamp('expires_at')->nullable();
            $table->string('broker_id')->nullable();
            $table->string('account_id')->nullable();
            $table->timestamps();

            $table->index(['agent_name', 'status', 'created_at']);
            $table->index(['symbol', 'status', 'created_at']);
        });

        // External Positions (imported from brokers)
        Schema::create('external_positions', function (Blueprint $table) {
            $table->id();
            $table->string('broker');
            $table->string('account_id');
            $table->string('account_name')->default('');
            $table->string('symbol');
            $table->string('description')->default('');
            $table->decimal('quantity', 20, 8);
            $table->decimal('cost_basis', 20, 8)->nullable();
            $table->decimal('current_value', 20, 8);
            $table->decimal('last_price', 20, 8);
            $table->timestamp('imported_at');
            $table->timestamps();

            $table->index(['broker', 'imported_at']);
            $table->index(['symbol', 'imported_at']);
        });

        // External Balances (imported from brokers)
        Schema::create('external_balances', function (Blueprint $table) {
            $table->id();
            $table->string('broker');
            $table->string('account_id');
            $table->string('account_name')->default('');
            $table->decimal('net_liquidation', 20, 8);
            $table->decimal('cash', 20, 8)->default(0);
            $table->timestamp('imported_at');
            $table->timestamps();

            $table->index(['broker', 'imported_at']);
        });

        // Risk Events
        Schema::create('risk_events', function (Blueprint $table) {
            $table->id();
            $table->string('event_type');
            $table->text('details')->nullable();
            $table->timestamps();

            $table->index(['event_type', 'created_at']);
        });

        // Performance Snapshots
        Schema::create('performance_snapshots', function (Blueprint $table) {
            $table->id();
            $table->string('agent_name');
            $table->integer('opportunities_generated');
            $table->integer('opportunities_executed');
            $table->decimal('win_rate', 5, 4);
            $table->decimal('total_pnl', 20, 8)->nullable();
            $table->decimal('daily_pnl', 20, 8)->nullable();
            $table->decimal('daily_pnl_pct', 8, 4)->nullable();
            $table->decimal('sharpe_ratio', 8, 4)->nullable();
            $table->decimal('max_drawdown', 8, 4)->nullable();
            $table->decimal('avg_win', 20, 8)->nullable();
            $table->decimal('avg_loss', 20, 8)->nullable();
            $table->decimal('profit_factor', 8, 4)->nullable();
            $table->integer('total_trades')->nullable();
            $table->integer('open_positions')->nullable();
            $table->timestamps();

            $table->index(['agent_name', 'created_at']);
        });

        // Opportunity Snapshots
        Schema::create('opportunity_snapshots', function (Blueprint $table) {
            $table->string('opportunity_id')->primary();
            $table->jsonb('snapshot_data');
            $table->timestamps();

            $table->foreign('opportunity_id')->references('id')->on('opportunities')->onDelete('cascade');
        });

        // Execution Quality (slippage tracking)
        Schema::create('execution_quality', function (Blueprint $table) {
            $table->id();
            $table->string('opportunity_id');
            $table->string('agent_name');
            $table->string('broker_id');
            $table->string('symbol');
            $table->string('side');
            $table->decimal('expected_price', 20, 8);
            $table->decimal('actual_price', 20, 8);
            $table->decimal('quantity', 20, 8);
            $table->decimal('slippage_bps', 8, 4);
            $table->timestamp('filled_at');
            $table->timestamps();

            $table->index(['agent_name', 'filled_at']);
            $table->index(['symbol', 'filled_at']);
        });

        // Execution Cost Events
        Schema::create('execution_cost_events', function (Blueprint $table) {
            $table->id();
            $table->string('opportunity_id')->nullable();
            $table->unsignedBigInteger('tracked_position_id')->nullable();
            $table->string('order_id')->unique();
            $table->string('agent_name')->nullable();
            $table->string('symbol');
            $table->string('broker_id')->nullable();
            $table->string('account_id')->nullable();
            $table->string('side');
            $table->string('order_type')->nullable();
            $table->timestamp('decision_time');
            $table->decimal('decision_bid', 20, 8)->nullable();
            $table->decimal('decision_ask', 20, 8)->nullable();
            $table->decimal('decision_last', 20, 8)->nullable();
            $table->decimal('decision_price', 20, 8)->nullable();
            $table->timestamp('fill_time')->nullable();
            $table->decimal('fill_price', 20, 8)->nullable();
            $table->decimal('filled_quantity', 20, 8);
            $table->decimal('fees_total', 20, 8);
            $table->decimal('spread_bps', 8, 4)->nullable();
            $table->decimal('slippage_bps', 8, 4)->nullable();
            $table->decimal('notional', 20, 8)->nullable();
            $table->string('status');
            $table->string('fill_source')->default('immediate');
            $table->timestamps();

            $table->index(['agent_name', 'decision_time']);
            $table->index(['symbol', 'decision_time']);
            $table->index(['broker_id', 'decision_time']);
        });

        // Execution Cost Stats (aggregated)
        Schema::create('execution_cost_stats', function (Blueprint $table) {
            $table->id();
            $table->string('group_type');
            $table->string('group_key');
            $table->string('window_label');
            $table->integer('trade_count');
            $table->decimal('avg_spread_bps', 8, 4)->nullable();
            $table->decimal('median_spread_bps', 8, 4)->nullable();
            $table->decimal('avg_slippage_bps', 8, 4)->nullable();
            $table->decimal('median_slippage_bps', 8, 4)->nullable();
            $table->decimal('p95_slippage_bps', 8, 4)->nullable();
            $table->decimal('avg_fee_dollars', 20, 8);
            $table->decimal('rejection_rate', 5, 4)->nullable();
            $table->decimal('partial_fill_rate', 5, 4)->nullable();
            $table->timestamps();

            $table->unique(['group_type', 'group_key', 'window_label']);
            $table->index(['group_type', 'group_key']);
        });

        // Trade Analytics
        Schema::create('trade_analytics', function (Blueprint $table) {
            $table->unsignedBigInteger('tracked_position_id')->primary();
            $table->string('opportunity_id')->nullable();
            $table->string('agent_name');
            $table->string('signal')->nullable();
            $table->string('symbol');
            $table->string('side');
            $table->string('broker_id')->nullable();
            $table->string('account_id')->nullable();
            $table->timestamp('entry_time');
            $table->timestamp('exit_time');
            $table->decimal('hold_minutes', 10, 2);
            $table->decimal('entry_price', 20, 8);
            $table->decimal('exit_price', 20, 8);
            $table->integer('entry_quantity');
            $table->decimal('entry_fees', 20, 8);
            $table->decimal('exit_fees', 20, 8);
            $table->decimal('gross_pnl', 20, 8);
            $table->decimal('net_pnl', 20, 8);
            $table->decimal('gross_return_pct', 8, 4);
            $table->decimal('net_return_pct', 8, 4);
            $table->string('realized_outcome');
            $table->string('exit_reason')->nullable();
            $table->decimal('confidence', 5, 4)->nullable();
            $table->string('confidence_bucket')->nullable();
            $table->string('strategy_version')->nullable();
            $table->string('regime_label')->nullable();
            $table->string('trend_regime')->nullable();
            $table->string('volatility_regime')->nullable();
            $table->string('liquidity_regime')->nullable();
            $table->decimal('execution_slippage_bps', 8, 4)->nullable();
            $table->decimal('entry_spread_bps', 8, 4)->nullable();
            $table->string('order_type')->nullable();
            $table->timestamps();

            $table->foreign('tracked_position_id')->references('id')->on('tracked_positions')->onDelete('cascade');
            $table->index(['agent_name', 'exit_time']);
            $table->index(['symbol', 'agent_name']);
            $table->index(['trend_regime', 'agent_name']);
        });

        // Consensus Votes (multi-agent coordination)
        Schema::create('consensus_votes', function (Blueprint $table) {
            $table->string('symbol');
            $table->string('side');
            $table->string('agent_name');
            $table->string('opportunity_id');
            $table->timestamp('voted_at');

            $table->primary(['symbol', 'side', 'agent_name']);
            $table->index(['symbol', 'side', 'voted_at']);
        });

        // WhatsApp Sessions
        Schema::create('whatsapp_sessions', function (Blueprint $table) {
            $table->string('phone')->primary();
            $table->timestamp('last_inbound_at');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('trade_analytics');
        Schema::dropIfExists('execution_cost_stats');
        Schema::dropIfExists('execution_cost_events');
        Schema::dropIfExists('execution_quality');
        Schema::dropIfExists('opportunity_snapshots');
        Schema::dropIfExists('performance_snapshots');
        Schema::dropIfExists('consensus_votes');
        Schema::dropIfExists('whatsapp_sessions');
        Schema::dropIfExists('risk_events');
        Schema::dropIfExists('external_balances');
        Schema::dropIfExists('external_positions');
        Schema::dropIfExists('tracked_positions');
        Schema::dropIfExists('trade_executions');
        Schema::dropIfExists('opportunities');
    }
};
