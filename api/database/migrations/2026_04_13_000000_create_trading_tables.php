<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('opportunities', function (Blueprint $table) {
            $table->text('id')->primary();
            $table->text('agent_name');
            $table->text('symbol');
            $table->text('signal');
            $table->double('confidence');
            $table->text('reasoning');
            $table->text('suggested_trade')->nullable();
            $table->text('status')->default('pending');
            $table->text('expires_at')->nullable();
            $table->text('data')->nullable();
            $table->text('created_at');
            $table->text('updated_at');
        });

        Schema::create('trades', function (Blueprint $table) {
            $table->id('id');
            $table->text('order_result');
            $table->text('risk_evaluation')->nullable();
            $table->text('agent_name')->nullable();
            $table->text('created_at');
        });

        Schema::create('risk_events', function (Blueprint $table) {
            $table->id('id');
            $table->text('event_type');
            $table->text('details')->nullable();
            $table->text('created_at');
        });

        Schema::create('performance_snapshots', function (Blueprint $table) {
            $table->id('id');
            $table->text('agent_name');
            $table->text('timestamp');
            $table->integer('opportunities_generated');
            $table->integer('opportunities_executed');
            $table->double('win_rate');
            $table->text('total_pnl')->nullable();
            $table->text('daily_pnl')->nullable();
            $table->double('daily_pnl_pct')->nullable();
            $table->double('sharpe_ratio')->nullable();
            $table->double('max_drawdown')->nullable();
            $table->text('avg_win')->nullable();
            $table->text('avg_loss')->nullable();
            $table->double('profit_factor')->nullable();
            $table->integer('total_trades')->nullable();
            $table->integer('open_positions')->nullable();
        });

        Schema::create('opportunity_snapshots', function (Blueprint $table) {
            $table->text('snapshot_data');
            $table->text('created_at');
        });

        Schema::create('whatsapp_sessions', function (Blueprint $table) {
            $table->text('phone')->primary();
            $table->text('last_inbound_at');
        });

        Schema::create('tracked_positions', function (Blueprint $table) {
            $table->id('id');
            $table->text('agent_name');
            $table->text('opportunity_id');
            $table->text('symbol');
            $table->text('side');
            $table->text('entry_price');
            $table->integer('entry_quantity');
            $table->text('entry_fees')->default('0');
            $table->text('entry_time');
            $table->text('exit_price')->nullable();
            $table->text('exit_fees')->nullable();
            $table->text('exit_time')->nullable();
            $table->text('exit_reason')->nullable();
            $table->text('max_adverse_excursion')->default('0');
            $table->text('status')->default('open');
            $table->text('expires_at')->nullable();
            $table->text('broker_id')->nullable();
            $table->text('account_id')->nullable();
            $table->text('created_at');
        });

        Schema::create('trust_events', function (Blueprint $table) {
            $table->id('id');
            $table->text('agent_name');
            $table->text('old_level');
            $table->text('new_level');
            $table->text('changed_by');
            $table->text('changed_at');
        });

        Schema::create('agent_overrides', function (Blueprint $table) {
            $table->text('agent_name')->primary();
            $table->text('trust_level')->nullable();
            $table->text('runtime_parameters')->nullable();
            $table->text('updated_at');
        });

        Schema::create('backtest_results', function (Blueprint $table) {
            $table->id('id');
            $table->text('agent_name');
            $table->text('parameters');
            $table->double('sharpe_ratio')->nullable();
            $table->double('profit_factor')->nullable();
            $table->text('total_pnl')->nullable();
            $table->double('max_drawdown')->nullable();
            $table->double('win_rate')->nullable();
            $table->integer('total_trades')->nullable();
            $table->text('run_date');
            $table->text('data_start');
            $table->text('data_end');
        });

        Schema::create('tournament_rounds', function (Blueprint $table) {
            $table->id('id');
            $table->text('agent_name');
            $table->text('status')->default('running');
            $table->text('champion_params');
            $table->text('started_at');
            $table->text('ended_at')->nullable();
            $table->text('winner_params')->nullable();
            $table->double('winner_sharpe')->nullable();
            $table->double('champion_sharpe')->nullable();
        });

        Schema::create('tournament_variants', function (Blueprint $table) {
            $table->id('id');
            $table->text('variant_label');
            $table->text('parameters');
            $table->double('sharpe_ratio')->nullable();
            $table->double('profit_factor')->nullable();
            $table->text('total_pnl')->nullable();
            $table->integer('total_trades')->nullable()->default(0);
        });

        Schema::create('llm_lessons', function (Blueprint $table) {
            $table->id('id');
            $table->text('agent_name');
            $table->text('opportunity_id');
            $table->text('category');
            $table->text('lesson');
            $table->text('applies_to');
            $table->text('created_at');
            $table->text('archived_at')->nullable();
        });

        Schema::create('llm_prompt_versions', function (Blueprint $table) {
            $table->id('id');
            $table->text('agent_name');
            $table->integer('version');
            $table->text('rules');
            $table->text('performance_at_creation')->nullable();
            $table->text('created_at');
        });

        Schema::create('external_positions', function (Blueprint $table) {
            $table->id('id');
            $table->text('broker');
            $table->text('account_id');
            $table->text('account_name')->default('');
            $table->text('symbol');
            $table->text('description')->default('');
            $table->text('quantity');
            $table->text('cost_basis')->nullable();
            $table->text('current_value');
            $table->text('last_price');
            $table->text('imported_at');
        });

        Schema::create('external_balances', function (Blueprint $table) {
            $table->id('id');
            $table->text('broker');
            $table->text('account_id');
            $table->text('account_name')->default('');
            $table->text('net_liquidation');
            $table->text('cash')->default('0');
            $table->text('imported_at');
        });

        Schema::create('consensus_votes', function (Blueprint $table) {
            $table->text('symbol');
            $table->text('side');
            $table->text('agent_name');
            $table->text('opportunity_id');
            $table->text('voted_at');
            $table->text('PRIMARY')->nullable();
        });

        Schema::create('leaderboard_cache', function (Blueprint $table) {
            $table->integer('id')->nullable();
            $table->text('rankings_json');
            $table->text('last_processed_snapshot_at');
            $table->text('updated_at');
            $table->text('source')->default('live');
        });

        Schema::create('agent_remembr_map', function (Blueprint $table) {
            $table->text('agent_name')->primary();
            $table->text('remembr_agent_id');
            $table->text('remembr_token')->nullable();
        });

        Schema::create('trade_autopsies', function (Blueprint $table) {
            $table->integer('position_id')->nullable();
            $table->text('autopsy_text');
            $table->text('created_at');
        });

        Schema::create('daily_briefs', function (Blueprint $table) {
            $table->text('date')->primary();
            $table->text('brief_text');
            $table->text('created_at');
        });

        Schema::create('convergence_syntheses', function (Blueprint $table) {
            $table->text('convergence_id')->primary();
            $table->text('synthesis_text');
            $table->text('created_at');
        });

        Schema::create('execution_quality', function (Blueprint $table) {
            $table->id('id');
            $table->text('opportunity_id');
            $table->text('agent_name');
            $table->text('broker_id');
            $table->text('symbol');
            $table->text('side');
            $table->text('expected_price');
            $table->text('actual_price');
            $table->text('quantity');
            $table->double('slippage_bps');
            $table->text('filled_at');
        });

        Schema::create('shadow_executions', function (Blueprint $table) {
            $table->text('id')->primary();
            $table->text('opportunity_id');
            $table->text('agent_name');
            $table->text('symbol');
            $table->text('side');
            $table->text('action_level');
            $table->text('decision_status');
            $table->text('expected_entry_price')->nullable();
            $table->text('expected_quantity')->nullable();
            $table->text('expected_notional')->nullable();
            $table->text('entry_price_source')->nullable();
            $table->jsonb('opportunity_snapshot')->nullable();
            $table->jsonb('risk_snapshot')->nullable();
            $table->jsonb('sizing_snapshot')->nullable();
            $table->jsonb('regime_snapshot')->nullable();
            $table->jsonb('health_snapshot')->nullable();
            $table->text('opened_at');
            $table->text('resolve_after');
            $table->text('resolved_at')->nullable();
            $table->text('resolution_status')->default('pending');
            $table->text('resolution_price')->nullable();
            $table->text('pnl')->nullable();
            $table->double('return_bps')->nullable();
            $table->double('max_favorable_bps')->nullable();
            $table->double('max_adverse_bps')->nullable();
            $table->jsonb('resolution_notes')->nullable();
        });

        Schema::create('position_exit_rules', function (Blueprint $table) {
            $table->integer('position_id')->nullable();
            $table->text('rules_json');
            $table->text('created_at');
        });

        Schema::create('bittensor_raw_forecasts', function (Blueprint $table) {
            $table->id('id');
            $table->text('window_id');
            $table->text('request_uuid');
            $table->text('collected_at');
            $table->text('stream_id');
            $table->integer('topic_id');
            $table->integer('schema_id');
            $table->text('symbol');
            $table->text('timeframe');
            $table->text('feature_ids');
            $table->integer('prediction_size');
            $table->integer('miner_uid')->nullable();
            $table->text('miner_hotkey');
            $table->text('predictions');
            $table->text('hashed_predictions')->nullable();
            $table->integer('hash_verified')->default(0);
            $table->double('incentive_score')->nullable();
            $table->double('vtrust')->nullable();
            $table->double('stake_tao')->nullable();
            $table->integer('metagraph_block')->nullable();
            $table->text('created_at');
        });

        Schema::create('bittensor_derived_views', function (Blueprint $table) {
            $table->text('window_id')->primary();
            $table->text('symbol');
            $table->text('timeframe');
            $table->text('timestamp');
            $table->integer('responder_count');
            $table->integer('bullish_count');
            $table->integer('bearish_count');
            $table->integer('flat_count');
            $table->double('weighted_direction');
            $table->double('weighted_expected_return');
            $table->double('agreement_ratio');
            $table->double('equal_weight_direction');
            $table->double('equal_weight_expected_return');
            $table->integer('is_low_confidence')->default(0);
            $table->text('derivation_version');
            $table->text('evaluation_status')->default('pending');
            $table->text('created_at');
        });

        Schema::create('bittensor_realized_windows', function (Blueprint $table) {
            $table->text('window_id')->primary();
            $table->text('symbol');
            $table->text('timeframe');
            $table->text('realized_path');
            $table->double('realized_return');
            $table->integer('bars_used');
            $table->text('source');
            $table->text('captured_at');
            $table->text('created_at');
        });

        Schema::create('bittensor_accuracy_records', function (Blueprint $table) {
            $table->id('id');
            $table->text('window_id');
            $table->text('miner_hotkey');
            $table->text('symbol');
            $table->text('timeframe');
            $table->integer('direction_correct');
            $table->double('predicted_return');
            $table->double('actual_return');
            $table->double('magnitude_error');
            $table->double('path_correlation')->nullable();
            $table->integer('outcome_bars');
            $table->text('scoring_version');
            $table->text('evaluated_at');
            $table->text('created_at');
        });

        Schema::create('bittensor_miner_rankings', function (Blueprint $table) {
            $table->text('miner_hotkey')->primary();
            $table->integer('windows_evaluated');
            $table->double('direction_accuracy');
            $table->double('mean_magnitude_error');
            $table->double('mean_path_correlation')->nullable();
            $table->double('internal_score');
            $table->double('latest_incentive_score')->nullable();
            $table->double('hybrid_score');
            $table->double('alpha_used');
            $table->text('updated_at');
        });

        Schema::create('execution_cost_events', function (Blueprint $table) {
            $table->id('id');
            $table->text('opportunity_id')->nullable();
            $table->integer('tracked_position_id')->nullable();
            $table->text('order_id');
            $table->text('agent_name')->nullable();
            $table->text('symbol');
            $table->text('broker_id')->nullable();
            $table->text('account_id')->nullable();
            $table->text('side');
            $table->text('order_type')->nullable();
            $table->text('decision_time');
            $table->text('decision_bid')->nullable();
            $table->text('decision_ask')->nullable();
            $table->text('decision_last')->nullable();
            $table->text('decision_price')->nullable();
            $table->text('fill_time')->nullable();
            $table->text('fill_price')->nullable();
            $table->text('filled_quantity');
            $table->text('fees_total');
            $table->double('spread_bps')->nullable();
            $table->double('slippage_bps')->nullable();
            $table->text('notional')->nullable();
            $table->text('status');
            $table->text('fill_source')->default('immediate');
            $table->text('created_at');
        });

        Schema::create('execution_cost_stats', function (Blueprint $table) {
            $table->id('id');
            $table->text('group_type');
            $table->text('group_key');
            $table->text('window_label');
            $table->integer('trade_count');
            $table->double('avg_spread_bps')->nullable();
            $table->double('median_spread_bps')->nullable();
            $table->double('avg_slippage_bps')->nullable();
            $table->double('median_slippage_bps')->nullable();
            $table->double('p95_slippage_bps')->nullable();
            $table->text('avg_fee_dollars');
            $table->double('rejection_rate')->nullable();
            $table->double('partial_fill_rate')->nullable();
            $table->text('created_at');
            $table->text('updated_at');
        });

        Schema::create('trade_analytics', function (Blueprint $table) {
            $table->integer('tracked_position_id')->nullable();
            $table->text('opportunity_id')->nullable();
            $table->text('agent_name');
            $table->text('signal')->nullable();
            $table->text('symbol');
            $table->text('side');
            $table->text('broker_id')->nullable();
            $table->text('account_id')->nullable();
            $table->text('entry_time');
            $table->text('exit_time');
            $table->double('hold_minutes');
            $table->text('entry_price');
            $table->text('exit_price');
            $table->integer('entry_quantity');
            $table->text('entry_fees');
            $table->text('exit_fees');
            $table->text('gross_pnl');
            $table->text('net_pnl');
            $table->double('gross_return_pct');
            $table->double('net_return_pct');
            $table->text('realized_outcome');
            $table->text('exit_reason')->nullable();
            $table->double('confidence')->nullable();
            $table->text('confidence_bucket')->nullable();
            $table->text('strategy_version')->nullable();
            $table->text('regime_label')->nullable();
            $table->text('trend_regime')->nullable();
            $table->text('volatility_regime')->nullable();
            $table->text('liquidity_regime')->nullable();
            $table->double('execution_slippage_bps')->nullable();
            $table->double('entry_spread_bps')->nullable();
            $table->text('order_type')->nullable();
            $table->text('created_at');
            $table->text('updated_at');
        });

        Schema::create('strategy_confidence_calibration', function (Blueprint $table) {
            $table->text('agent_name');
            $table->text('confidence_bucket');
            $table->text('window_label');
            $table->integer('trade_count');
            $table->double('win_rate');
            $table->text('avg_net_pnl');
            $table->double('avg_net_return_pct');
            $table->text('expectancy');
            $table->double('profit_factor')->nullable();
            $table->text('max_drawdown')->nullable();
            $table->double('calibrated_score')->nullable();
            $table->text('sample_quality');
            $table->text('created_at');
            $table->text('updated_at');
            $table->text('UNIQUE')->nullable();
        });

        Schema::create('strategy_health', function (Blueprint $table) {
            $table->text('agent_name')->primary();
            $table->text('status');
            $table->double('health_score')->nullable();
            $table->text('rolling_expectancy')->nullable();
            $table->text('rolling_net_pnl')->nullable();
            $table->text('rolling_drawdown')->nullable();
            $table->double('rolling_win_rate')->nullable();
            $table->integer('rolling_trade_count')->default(0);
            $table->double('throttle_multiplier')->nullable();
            $table->text('trigger_reason')->nullable();
            $table->text('cooldown_until')->nullable();
            $table->text('manual_override')->nullable();
            $table->text('updated_at');
        });

        Schema::create('strategy_health_events', function (Blueprint $table) {
            $table->id('id');
            $table->text('agent_name');
            $table->text('old_status')->nullable();
            $table->text('new_status');
            $table->text('reason');
            $table->text('metrics_snapshot')->default('{}');
            $table->text('created_at');
            $table->text('actor');
        });

        Schema::create('signal_features', function (Blueprint $table) {
            $table->text('opportunity_id')->primary();
            $table->text('agent_name');
            $table->text('symbol');
            $table->text('signal');
            $table->text('asset_type')->default('STOCK');
            $table->text('broker_id')->nullable();
            $table->double('confidence');
            $table->text('opportunity_timestamp');
            $table->text('captured_at');
            $table->double('capture_delay_ms')->nullable();
            $table->text('feature_version')->default('1.0');
            $table->text('quote_bid')->nullable();
            $table->text('quote_ask')->nullable();
            $table->text('quote_last')->nullable();
            $table->text('quote_mid')->nullable();
            $table->double('spread_bps')->nullable();
            $table->double('rsi_14')->nullable();
            $table->double('sma_20')->nullable();
            $table->double('ema_20')->nullable();
            $table->double('macd_line')->nullable();
            $table->double('macd_signal')->nullable();
            $table->double('macd_histogram')->nullable();
            $table->double('bollinger_upper')->nullable();
            $table->double('bollinger_middle')->nullable();
            $table->double('bollinger_lower')->nullable();
            $table->double('bollinger_pct_b')->nullable();
            $table->double('atr_14')->nullable();
            $table->double('realized_vol_20d')->nullable();
            $table->double('relative_volume_20d')->nullable();
            $table->double('distance_to_sma20_pct')->nullable();
            $table->double('distance_to_ema20_pct')->nullable();
            $table->text('trend_regime')->nullable();
            $table->text('volatility_regime')->nullable();
            $table->text('liquidity_regime')->nullable();
            $table->text('event_regime')->nullable();
            $table->text('market_state')->nullable();
            $table->text('market_proxy_symbol')->nullable();
            $table->double('market_proxy_rsi_14')->nullable();
            $table->double('market_proxy_return_1d')->nullable();
            $table->text('feature_payload')->default('{}');
            $table->text('capture_status')->default('captured');
            $table->text('capture_error')->nullable();
            $table->text('created_at');
            $table->text('updated_at');
        });

        Schema::create('tournament_audit_log', function (Blueprint $table) {
            $table->id('id');
            $table->text('agent_name');
            $table->integer('from_stage');
            $table->integer('to_stage');
            $table->text('reason');
            $table->text('ai_analysis')->default('');
            $table->text('ai_recommendation')->default('');
            $table->text('timestamp');
            $table->text('overridden_by')->nullable();
        });

        Schema::create('agent_stages', function (Blueprint $table) {
            $table->text('agent_name')->primary();
            $table->integer('current_stage')->default(0);
            $table->text('updated_at');
        });

        Schema::create('arb_spread_observations', function (Blueprint $table) {
            $table->id('id');
            $table->text('kalshi_ticker');
            $table->text('poly_ticker');
            $table->double('match_score');
            $table->integer('kalshi_cents');
            $table->integer('poly_cents');
            $table->integer('gap_cents');
            $table->double('kalshi_volume')->default(0);
            $table->double('poly_volume')->default(0);
            $table->text('observed_at');
            $table->boolean('is_claimed')->default(false);
            $table->text('claimed_at')->nullable();
            $table->text('claimed_by')->nullable();
        });

        Schema::create('arb_trades', function (Blueprint $table) {
            $table->text('id')->primary();
            $table->text('symbol_a');
            $table->text('symbol_b');
            $table->integer('expected_profit_bps');
            $table->text('sequencing');
            $table->text('state');
            $table->text('error_message')->nullable();
            $table->text('created_at');
            $table->text('updated_at');
        });

        Schema::create('arb_legs', function (Blueprint $table) {
            $table->text('leg_name');
            $table->text('broker_id');
            $table->text('order_data');
            $table->text('fill_price')->nullable();
            $table->text('fill_quantity');
            $table->text('status');
            $table->text('external_order_id')->nullable();
            $table->text('PRIMARY')->nullable();
        });

        Schema::create('agent_registry', function (Blueprint $table) {
            $table->id('id');
            $table->text('name');
            $table->text('strategy');
            $table->text('schedule')->default('continuous');
            $table->integer('interval_or_cron');
            $table->jsonb('universe')->default('[]');
            $table->jsonb('parameters')->default('{}');
            $table->text('status')->default('active');
            $table->text('trust_level')->default('monitored');
            $table->jsonb('runtime_overrides')->default('{}');
            $table->jsonb('promotion_criteria')->default('{}');
            $table->boolean('shadow_mode')->default(false);
            $table->text('created_by')->default('human');
            $table->text('parent_name')->nullable();
            $table->integer('generation');
            $table->jsonb('creation_context')->default('{}');
            $table->timestampTz('created_at');
            $table->timestampTz('updated_at');
        });


        // Indexes
        // CREATE INDEX IF NOT EXISTS idx_opp_agent ON opportunities(agent_name)
        // CREATE INDEX IF NOT EXISTS idx_opp_symbol ON opportunities(symbol)
        // CREATE INDEX IF NOT EXISTS idx_opp_status ON opportunities(status)
        // CREATE INDEX IF NOT EXISTS idx_trades_opp ON trades(opportunity_id)
        // CREATE INDEX IF NOT EXISTS idx_perf_agent ON performance_snapshots(agent_name)
        // CREATE INDEX IF NOT EXISTS idx_tracked_agent_status ON tracked_positions(agent_name, status)
        // CREATE INDEX IF NOT EXISTS idx_tracked_symbol ON tracked_positions(symbol, status)
        // CREATE INDEX IF NOT EXISTS idx_backtest_agent ON backtest_results(agent_name, run_date)
        // CREATE INDEX IF NOT EXISTS idx_ext_pos_broker ON external_positions(broker)
        // CREATE INDEX IF NOT EXISTS idx_ext_pos_symbol ON external_positions(symbol)
        // CREATE INDEX IF NOT EXISTS idx_ext_bal_broker ON external_balances(broker)
        // CREATE INDEX IF NOT EXISTS idx_consensus_window ON consensus_votes(symbol, side, voted_at)
        // CREATE INDEX IF NOT EXISTS idx_exec_quality_agent ON execution_quality(agent_name, filled_at)
        // CREATE INDEX IF NOT EXISTS idx_shadow_executions_agent_opened ON shadow_executions(agent_name, opened_at DESC)
        // CREATE INDEX IF NOT EXISTS idx_shadow_executions_due ON shadow_executions(resolution_status, resolve_after)
        // CREATE INDEX IF NOT EXISTS idx_shadow_executions_opportunity ON shadow_executions(opportunity_id)
        // CREATE INDEX IF NOT EXISTS idx_shadow_executions_symbol_opened ON shadow_executions(symbol, opened_at DESC)
        // CREATE INDEX IF NOT EXISTS idx_bt_raw_window ON bittensor_raw_forecasts(window_id)
        // CREATE INDEX IF NOT EXISTS idx_bt_raw_symbol_time ON bittensor_raw_forecasts(symbol, timeframe, collected_at)
        // CREATE INDEX IF NOT EXISTS idx_bt_raw_miner ON bittensor_raw_forecasts(miner_hotkey, collected_at)
        // CREATE INDEX IF NOT EXISTS idx_bt_view_symbol_time ON bittensor_derived_views(symbol, timeframe, timestamp)
        // CREATE INDEX IF NOT EXISTS idx_bt_realized_symbol ON bittensor_realized_windows(symbol, timeframe, captured_at)
        // CREATE INDEX IF NOT EXISTS idx_bt_acc_miner ON bittensor_accuracy_records(miner_hotkey, evaluated_at)
        // CREATE INDEX IF NOT EXISTS idx_bt_acc_window ON bittensor_accuracy_records(window_id, miner_hotkey)
        // CREATE INDEX IF NOT EXISTS idx_bt_acc_symbol ON bittensor_accuracy_records(symbol, timeframe, evaluated_at)
        // CREATE INDEX IF NOT EXISTS idx_bt_rank_hybrid ON bittensor_miner_rankings(hybrid_score DESC)
        // CREATE INDEX IF NOT EXISTS idx_bt_rank_internal ON bittensor_miner_rankings(internal_score DESC)
        // CREATE INDEX IF NOT EXISTS idx_ece_agent ON execution_cost_events(agent_name, decision_time)
        // CREATE INDEX IF NOT EXISTS idx_ece_symbol ON execution_cost_events(symbol, decision_time)
        // CREATE INDEX IF NOT EXISTS idx_ece_broker ON execution_cost_events(broker_id, decision_time)
        // CREATE INDEX IF NOT EXISTS idx_ecs_group ON execution_cost_stats(group_type, group_key)
        // CREATE INDEX IF NOT EXISTS idx_ta_agent_exit ON trade_analytics(agent_name, exit_time)
        // CREATE INDEX IF NOT EXISTS idx_ta_symbol ON trade_analytics(symbol, agent_name)
        // CREATE INDEX IF NOT EXISTS idx_ta_regime ON trade_analytics(trend_regime, agent_name)
        // CREATE INDEX IF NOT EXISTS idx_cc_agent_window ON strategy_confidence_calibration(agent_name, window_label)
        // CREATE INDEX IF NOT EXISTS idx_strategy_health_status ON strategy_health(status)
        // CREATE INDEX IF NOT EXISTS idx_she_agent_time ON strategy_health_events(agent_name, created_at)
        // CREATE INDEX IF NOT EXISTS idx_sf_agent_time ON signal_features(agent_name, opportunity_timestamp)
        // CREATE INDEX IF NOT EXISTS idx_sf_symbol_time ON signal_features(symbol, opportunity_timestamp)
        // CREATE INDEX IF NOT EXISTS idx_sf_signal_agent ON signal_features(signal, agent_name)
        // CREATE INDEX IF NOT EXISTS idx_tournament_audit_agent ON tournament_audit_log(agent_name, timestamp)
        // CREATE INDEX IF NOT EXISTS idx_arb_spread_pair ON arb_spread_observations(kalshi_ticker, poly_ticker, observed_at)
        // CREATE INDEX IF NOT EXISTS idx_arb_spread_gap ON arb_spread_observations(gap_cents, observed_at)
        // CREATE INDEX IF NOT EXISTS idx_arb_trades_state ON arb_trades(state)
        // CREATE INDEX IF NOT EXISTS idx_arb_legs_trade_id ON arb_legs(trade_id)
        // CREATE INDEX IF NOT EXISTS idx_agent_registry_name ON agent_registry(name)
        // CREATE INDEX IF NOT EXISTS idx_agent_registry_status ON agent_registry(status)
        // CREATE INDEX IF NOT EXISTS idx_agent_registry_strategy ON agent_registry(strategy)
        // CREATE INDEX IF NOT EXISTS idx_agent_registry_created_by ON agent_registry(created_by)
        // CREATE INDEX IF NOT EXISTS idx_agent_registry_parent ON agent_registry(parent_name)

        // Foreign Keys
        Schema::table('trades', function (Blueprint $table) {
            $table->foreign('opportunity_id')->references('id')->on('opportunities');
        });

        Schema::table('opportunity_snapshots', function (Blueprint $table) {
            $table->foreign('opportunity_id')->references('id')->on('opportunities');
        });

        Schema::table('arb_legs', function (Blueprint $table) {
            $table->foreign('trade_id')->references('id')->on('arb_trades')->onDelete('cascade');
        });

        // Composite Primary Keys
        Schema::table('consensus_votes', function (Blueprint $table) {
            $table->primary(['symbol', 'side', 'agent_name']);
        });

        Schema::table('arb_legs', function (Blueprint $table) {
            $table->primary(['trade_id', 'leg_name']);
        });

        // UNIQUE Constraints
        Schema::table('bittensor_raw_forecasts', function (Blueprint $table) {
            $table->unique(['window_id', 'miner_hotkey']);
        });

        Schema::table('execution_cost_stats', function (Blueprint $table) {
            $table->unique(['group_type', 'group_key', 'window_label']);
        });

        Schema::table('strategy_confidence_calibration', function (Blueprint $table) {
            $table->unique(['agent_name', 'confidence_bucket', 'window_label']);
        });

        // CHECK Constraints
        DB::statement('ALTER TABLE leaderboard_cache ADD CONSTRAINT chk_leaderboard_single_row CHECK (id = 1)');

        // Indexes
        Schema::table('opportunities', function (Blueprint $table) {
            $table->index(['agent_name', 'created_at']);
            $table->index('status');
        });

        Schema::table('tracked_positions', function (Blueprint $table) {
            $table->index(['agent_name', 'status']);
            $table->index('opportunity_id');
        });

        Schema::table('arb_spread_observations', function (Blueprint $table) {
            $table->index(['kalshi_ticker', 'poly_ticker', 'observed_at'], 'idx_arb_spread_pair');
            $table->index(['gap_cents', 'observed_at'], 'idx_arb_spread_gap');
        });

        Schema::table('arb_trades', function (Blueprint $table) {
            $table->index('state');
        });

        Schema::table('arb_legs', function (Blueprint $table) {
            $table->index('trade_id');
        });

        Schema::table('agent_registry', function (Blueprint $table) {
            $table->index('name');
            $table->index('status');
            $table->index('strategy');
            $table->index('created_by');
            $table->index('parent_name');
        });

        Schema::table('tournament_audit_log', function (Blueprint $table) {
            $table->index(['agent_name', 'timestamp']);
        });
    }

    public function down(): void
    {
        // Drop tables in reverse order
        Schema::dropIfExists('an');
        Schema::dropIfExists('agent_registry');
        Schema::dropIfExists('arb_legs');
        Schema::dropIfExists('arb_trades');
        Schema::dropIfExists('arb_spread_observations');
        Schema::dropIfExists('agent_stages');
        Schema::dropIfExists('tournament_audit_log');
        Schema::dropIfExists('signal_features');
        Schema::dropIfExists('strategy_health_events');
        Schema::dropIfExists('strategy_health');
        Schema::dropIfExists('strategy_confidence_calibration');
        Schema::dropIfExists('trade_analytics');
        Schema::dropIfExists('execution_cost_stats');
        Schema::dropIfExists('execution_cost_events');
        Schema::dropIfExists('bittensor_miner_rankings');
        Schema::dropIfExists('bittensor_accuracy_records');
        Schema::dropIfExists('bittensor_realized_windows');
        Schema::dropIfExists('bittensor_derived_views');
        Schema::dropIfExists('bittensor_raw_forecasts');
        Schema::dropIfExists('position_exit_rules');
        Schema::dropIfExists('shadow_executions');
        Schema::dropIfExists('execution_quality');
        Schema::dropIfExists('convergence_syntheses');
        Schema::dropIfExists('daily_briefs');
        Schema::dropIfExists('trade_autopsies');
        Schema::dropIfExists('agent_remembr_map');
        Schema::dropIfExists('leaderboard_cache');
        Schema::dropIfExists('consensus_votes');
        Schema::dropIfExists('external_balances');
        Schema::dropIfExists('external_positions');
        Schema::dropIfExists('llm_prompt_versions');
        Schema::dropIfExists('llm_lessons');
        Schema::dropIfExists('tournament_variants');
        Schema::dropIfExists('tournament_rounds');
        Schema::dropIfExists('backtest_results');
        Schema::dropIfExists('agent_overrides');
        Schema::dropIfExists('trust_events');
        Schema::dropIfExists('tracked_positions');
        Schema::dropIfExists('whatsapp_sessions');
        Schema::dropIfExists('opportunity_snapshots');
        Schema::dropIfExists('performance_snapshots');
        Schema::dropIfExists('risk_events');
        Schema::dropIfExists('trades');
        Schema::dropIfExists('opportunities');
    }
};
