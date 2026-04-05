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
        // Agent Registry (replaces agents.yaml)
        Schema::create('agent_registry', function (Blueprint $table) {
            $table->id();
            $table->string('name')->unique();
            $table->string('strategy');
            $table->string('schedule')->default('continuous');
            $table->integer('interval_or_cron')->default(60);
            $table->jsonb('universe')->default('[]');
            $table->jsonb('parameters')->default('{}');
            $table->string('status')->default('active')->index();
            $table->string('trust_level')->default('monitored');
            $table->jsonb('runtime_overrides')->default('{}');
            $table->jsonb('promotion_criteria')->default('{}');
            $table->boolean('shadow_mode')->default(false);
            $table->string('created_by')->default('human')->index();
            $table->string('parent_name')->nullable()->index();
            $table->integer('generation')->default(1);
            $table->jsonb('creation_context')->default('{}');
            $table->timestamps();

            $table->index(['name', 'status']);
            $table->index('strategy');
        });

        // Agent Overrides
        Schema::create('agent_overrides', function (Blueprint $table) {
            $table->string('agent_name')->primary();
            $table->string('trust_level')->nullable();
            $table->jsonb('runtime_parameters')->nullable();
            $table->timestamps();
        });

        // Trust Events
        Schema::create('trust_events', function (Blueprint $table) {
            $table->id();
            $table->string('agent_name');
            $table->string('old_level');
            $table->string('new_level');
            $table->string('changed_by');
            $table->timestamps();

            $table->index(['agent_name', 'created_at']);
        });

        // Agent Stages
        Schema::create('agent_stages', function (Blueprint $table) {
            $table->string('agent_name')->primary();
            $table->integer('current_stage')->default(0);
            $table->timestamps();
        });

        // Backtest Results
        Schema::create('backtest_results', function (Blueprint $table) {
            $table->id();
            $table->string('agent_name');
            $table->jsonb('parameters');
            $table->decimal('sharpe_ratio', 8, 4)->nullable();
            $table->decimal('profit_factor', 8, 4)->nullable();
            $table->decimal('total_pnl', 20, 8)->nullable();
            $table->decimal('max_drawdown', 8, 4)->nullable();
            $table->decimal('win_rate', 5, 4)->nullable();
            $table->integer('total_trades')->nullable();
            $table->date('run_date');
            $table->date('data_start');
            $table->date('data_end');
            $table->timestamps();

            $table->index(['agent_name', 'run_date']);
        });

        // Tournament Rounds
        Schema::create('tournament_rounds', function (Blueprint $table) {
            $table->id();
            $table->string('agent_name');
            $table->string('status')->default('running');
            $table->jsonb('champion_params');
            $table->timestamp('started_at');
            $table->timestamp('ended_at')->nullable();
            $table->jsonb('winner_params')->nullable();
            $table->decimal('winner_sharpe', 8, 4)->nullable();
            $table->decimal('champion_sharpe', 8, 4)->nullable();
            $table->timestamps();

            $table->index(['agent_name', 'status']);
        });

        // Tournament Variants
        Schema::create('tournament_variants', function (Blueprint $table) {
            $table->id();
            $table->foreignId('round_id')->constrained('tournament_rounds')->onDelete('cascade');
            $table->string('variant_label');
            $table->jsonb('parameters');
            $table->decimal('sharpe_ratio', 8, 4)->nullable();
            $table->decimal('profit_factor', 8, 4)->nullable();
            $table->decimal('total_pnl', 20, 8)->nullable();
            $table->integer('total_trades')->default(0);
            $table->timestamps();

            $table->index('round_id');
        });

        // Tournament Audit Log
        Schema::create('tournament_audit_log', function (Blueprint $table) {
            $table->id();
            $table->string('agent_name');
            $table->integer('from_stage');
            $table->integer('to_stage');
            $table->text('reason');
            $table->text('ai_analysis')->default('');
            $table->text('ai_recommendation')->default('');
            $table->string('overridden_by')->nullable();
            $table->timestamps();

            $table->index(['agent_name', 'created_at']);
        });

        // LLM Lessons
        Schema::create('llm_lessons', function (Blueprint $table) {
            $table->id();
            $table->string('agent_name');
            $table->string('opportunity_id');
            $table->string('category');
            $table->text('lesson');
            $table->string('applies_to');
            $table->timestamp('archived_at')->nullable();
            $table->timestamps();

            $table->index(['agent_name', 'archived_at']);
        });

        // LLM Prompt Versions
        Schema::create('llm_prompt_versions', function (Blueprint $table) {
            $table->id();
            $table->string('agent_name');
            $table->integer('version');
            $table->text('rules');
            $table->jsonb('performance_at_creation')->nullable();
            $table->timestamps();

            $table->index(['agent_name', 'version']);
        });

        // Position Exit Rules
        Schema::create('position_exit_rules', function (Blueprint $table) {
            $table->unsignedBigInteger('position_id')->primary();
            $table->jsonb('rules_json');
            $table->timestamps();

            $table->foreign('position_id')->references('id')->on('tracked_positions')->onDelete('cascade');
        });

        // Trade Autopsies
        Schema::create('trade_autopsies', function (Blueprint $table) {
            $table->unsignedBigInteger('position_id')->primary();
            $table->text('autopsy_text');
            $table->timestamps();

            $table->foreign('position_id')->references('id')->on('tracked_positions')->onDelete('cascade');
        });

        // Daily Briefs
        Schema::create('daily_briefs', function (Blueprint $table) {
            $table->date('date')->primary();
            $table->text('brief_text');
            $table->timestamps();
        });

        // Convergence Syntheses
        Schema::create('convergence_syntheses', function (Blueprint $table) {
            $table->string('convergence_id')->primary();
            $table->text('synthesis_text');
            $table->timestamps();
        });

        // Shadow Executions
        Schema::create('shadow_executions', function (Blueprint $table) {
            $table->string('id')->primary();
            $table->string('opportunity_id');
            $table->string('agent_name');
            $table->string('symbol');
            $table->string('side');
            $table->string('action_level');
            $table->string('decision_status');
            $table->decimal('expected_entry_price', 20, 8)->nullable();
            $table->decimal('expected_quantity', 20, 8)->nullable();
            $table->decimal('expected_notional', 20, 8)->nullable();
            $table->string('entry_price_source')->nullable();
            $table->jsonb('opportunity_snapshot')->nullable();
            $table->jsonb('risk_snapshot')->nullable();
            $table->jsonb('sizing_snapshot')->nullable();
            $table->jsonb('regime_snapshot')->nullable();
            $table->jsonb('health_snapshot')->nullable();
            $table->timestamp('opened_at');
            $table->timestamp('resolve_after');
            $table->timestamp('resolved_at')->nullable();
            $table->string('resolution_status')->default('pending');
            $table->decimal('resolution_price', 20, 8)->nullable();
            $table->decimal('pnl', 20, 8)->nullable();
            $table->decimal('return_bps', 8, 4)->nullable();
            $table->decimal('max_favorable_bps', 8, 4)->nullable();
            $table->decimal('max_adverse_bps', 8, 4)->nullable();
            $table->text('resolution_notes')->nullable();
            $table->timestamps();

            $table->index(['agent_name', 'opened_at']);
            $table->index(['resolution_status', 'resolve_after']);
            $table->index('opportunity_id');
            $table->index(['symbol', 'opened_at']);
        });

        // Strategy Confidence Calibration
        Schema::create('strategy_confidence_calibration', function (Blueprint $table) {
            $table->string('agent_name');
            $table->string('confidence_bucket');
            $table->string('window_label');
            $table->integer('trade_count');
            $table->decimal('win_rate', 5, 4);
            $table->decimal('avg_net_pnl', 20, 8);
            $table->decimal('avg_net_return_pct', 8, 4);
            $table->decimal('expectancy', 20, 8);
            $table->decimal('profit_factor', 8, 4)->nullable();
            $table->decimal('max_drawdown', 20, 8)->nullable();
            $table->decimal('calibrated_score', 8, 4)->nullable();
            $table->string('sample_quality');
            $table->timestamps();

            $table->primary(['agent_name', 'confidence_bucket', 'window_label'], 'scc_primary');
            $table->index(['agent_name', 'window_label']);
        });

        // Strategy Health
        Schema::create('strategy_health', function (Blueprint $table) {
            $table->string('agent_name')->primary();
            $table->string('status');
            $table->decimal('health_score', 5, 4)->nullable();
            $table->decimal('rolling_expectancy', 20, 8)->nullable();
            $table->decimal('rolling_net_pnl', 20, 8)->nullable();
            $table->decimal('rolling_drawdown', 20, 8)->nullable();
            $table->decimal('rolling_win_rate', 5, 4)->nullable();
            $table->integer('rolling_trade_count')->default(0);
            $table->decimal('throttle_multiplier', 5, 2)->nullable();
            $table->string('trigger_reason')->nullable();
            $table->timestamp('cooldown_until')->nullable();
            $table->string('manual_override')->nullable();
            $table->timestamps();

            $table->index('status');
        });

        // Strategy Health Events
        Schema::create('strategy_health_events', function (Blueprint $table) {
            $table->id();
            $table->string('agent_name');
            $table->string('old_status')->nullable();
            $table->string('new_status');
            $table->text('reason');
            $table->jsonb('metrics_snapshot')->default('{}');
            $table->string('actor');
            $table->timestamps();

            $table->index(['agent_name', 'created_at']);
        });

        // Signal Features
        Schema::create('signal_features', function (Blueprint $table) {
            $table->string('opportunity_id')->primary();
            $table->string('agent_name');
            $table->string('symbol');
            $table->string('signal');
            $table->string('asset_type')->default('STOCK');
            $table->string('broker_id')->nullable();
            $table->decimal('confidence', 5, 4);
            $table->timestamp('opportunity_timestamp');
            $table->timestamp('captured_at');
            $table->decimal('capture_delay_ms', 10, 2)->nullable();
            $table->string('feature_version')->default('1.0');
            $table->decimal('quote_bid', 20, 8)->nullable();
            $table->decimal('quote_ask', 20, 8)->nullable();
            $table->decimal('quote_last', 20, 8)->nullable();
            $table->decimal('quote_mid', 20, 8)->nullable();
            $table->decimal('spread_bps', 8, 4)->nullable();
            $table->decimal('rsi_14', 8, 4)->nullable();
            $table->decimal('sma_20', 20, 8)->nullable();
            $table->decimal('ema_20', 20, 8)->nullable();
            $table->decimal('macd_line', 20, 8)->nullable();
            $table->decimal('macd_signal', 20, 8)->nullable();
            $table->decimal('macd_histogram', 20, 8)->nullable();
            $table->decimal('bollinger_upper', 20, 8)->nullable();
            $table->decimal('bollinger_middle', 20, 8)->nullable();
            $table->decimal('bollinger_lower', 20, 8)->nullable();
            $table->decimal('bollinger_pct_b', 8, 4)->nullable();
            $table->decimal('atr_14', 20, 8)->nullable();
            $table->decimal('realized_vol_20d', 8, 4)->nullable();
            $table->decimal('relative_volume_20d', 8, 4)->nullable();
            $table->decimal('distance_to_sma20_pct', 8, 4)->nullable();
            $table->decimal('distance_to_ema20_pct', 8, 4)->nullable();
            $table->string('trend_regime')->nullable();
            $table->string('volatility_regime')->nullable();
            $table->string('liquidity_regime')->nullable();
            $table->string('event_regime')->nullable();
            $table->string('market_state')->nullable();
            $table->string('market_proxy_symbol')->nullable();
            $table->decimal('market_proxy_rsi_14', 8, 4)->nullable();
            $table->decimal('market_proxy_return_1d', 8, 4)->nullable();
            $table->jsonb('feature_payload')->default('{}');
            $table->string('capture_status')->default('captured');
            $table->text('capture_error')->nullable();
            $table->timestamps();

            $table->foreign('opportunity_id')->references('id')->on('opportunities')->onDelete('cascade');
            $table->index(['agent_name', 'opportunity_timestamp']);
            $table->index(['symbol', 'opportunity_timestamp']);
            $table->index(['signal', 'agent_name']);
        });

        // Leaderboard Cache
        Schema::create('leaderboard_cache', function (Blueprint $table) {
            $table->id()->default(1);
            $table->jsonb('rankings_json');
            $table->timestamp('last_processed_snapshot_at');
            $table->string('source')->default('live');
            $table->timestamps();
        });

        // Agent Remembr Map
        Schema::create('agent_remembr_map', function (Blueprint $table) {
            $table->string('agent_name')->primary();
            $table->string('remembr_agent_id');
            $table->string('remembr_token')->nullable();
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('agent_remembr_map');
        Schema::dropIfExists('leaderboard_cache');
        Schema::dropIfExists('signal_features');
        Schema::dropIfExists('strategy_health_events');
        Schema::dropIfExists('strategy_health');
        Schema::dropIfExists('strategy_confidence_calibration');
        Schema::dropIfExists('shadow_executions');
        Schema::dropIfExists('convergence_syntheses');
        Schema::dropIfExists('daily_briefs');
        Schema::dropIfExists('trade_autopsies');
        Schema::dropIfExists('position_exit_rules');
        Schema::dropIfExists('llm_prompt_versions');
        Schema::dropIfExists('llm_lessons');
        Schema::dropIfExists('tournament_audit_log');
        Schema::dropIfExists('tournament_variants');
        Schema::dropIfExists('tournament_rounds');
        Schema::dropIfExists('backtest_results');
        Schema::dropIfExists('agent_stages');
        Schema::dropIfExists('trust_events');
        Schema::dropIfExists('agent_overrides');
        Schema::dropIfExists('agent_registry');
    }
};
