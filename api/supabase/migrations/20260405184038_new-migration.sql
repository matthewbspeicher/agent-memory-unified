-- Trading System Schema Migration
-- Generated from Laravel migrations for Supabase PostgreSQL

-- Core Trading Tables

CREATE TABLE opportunities (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    signal TEXT NOT NULL,
    confidence DECIMAL(8, 4) NOT NULL,
    reasoning TEXT NOT NULL,
    suggested_trade TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    expires_at TIMESTAMPTZ,
    data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_opportunities_agent_name ON opportunities(agent_name, created_at);
CREATE INDEX idx_opportunities_symbol ON opportunities(symbol, created_at);
CREATE INDEX idx_opportunities_status ON opportunities(status);

CREATE TABLE trades (
    id BIGSERIAL PRIMARY KEY,
    opportunity_id TEXT REFERENCES opportunities(id) ON DELETE SET NULL,
    agent_name TEXT,
    order_result JSONB NOT NULL,
    risk_evaluation JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trades_opportunity ON trades(opportunity_id, created_at);
CREATE INDEX idx_trades_agent ON trades(agent_name, created_at);

CREATE TABLE tracked_positions (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    entry_quantity INTEGER NOT NULL,
    entry_fees DECIMAL(20, 8) NOT NULL DEFAULT 0,
    entry_time TIMESTAMPTZ NOT NULL,
    exit_price DECIMAL(20, 8),
    exit_fees DECIMAL(20, 8),
    exit_time TIMESTAMPTZ,
    exit_reason TEXT,
    max_adverse_excursion DECIMAL(20, 8) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    expires_at TIMESTAMPTZ,
    broker_id TEXT,
    account_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tracked_positions_agent ON tracked_positions(agent_name, status, created_at);
CREATE INDEX idx_tracked_positions_symbol ON tracked_positions(symbol, status, created_at);

CREATE TABLE external_positions (
    id BIGSERIAL PRIMARY KEY,
    broker TEXT NOT NULL,
    account_id TEXT NOT NULL,
    account_name TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    quantity DECIMAL(20, 8) NOT NULL,
    cost_basis DECIMAL(20, 8),
    current_value DECIMAL(20, 8) NOT NULL,
    last_price DECIMAL(20, 8) NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_external_positions_broker ON external_positions(broker, imported_at);
CREATE INDEX idx_external_positions_symbol ON external_positions(symbol, imported_at);

CREATE TABLE external_balances (
    id BIGSERIAL PRIMARY KEY,
    broker TEXT NOT NULL,
    account_id TEXT NOT NULL,
    account_name TEXT NOT NULL DEFAULT '',
    net_liquidation DECIMAL(20, 8) NOT NULL,
    cash DECIMAL(20, 8) NOT NULL DEFAULT 0,
    imported_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_external_balances_broker ON external_balances(broker, imported_at);

CREATE TABLE risk_events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_risk_events_type ON risk_events(event_type, created_at);

CREATE TABLE performance_snapshots (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    opportunities_generated INTEGER NOT NULL,
    opportunities_executed INTEGER NOT NULL,
    win_rate DECIMAL(5, 4) NOT NULL,
    total_pnl DECIMAL(20, 8),
    daily_pnl DECIMAL(20, 8),
    daily_pnl_pct DECIMAL(8, 4),
    sharpe_ratio DECIMAL(8, 4),
    max_drawdown DECIMAL(8, 4),
    avg_win DECIMAL(20, 8),
    avg_loss DECIMAL(20, 8),
    profit_factor DECIMAL(8, 4),
    total_trades INTEGER,
    open_positions INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_performance_snapshots_agent ON performance_snapshots(agent_name, created_at);

CREATE TABLE opportunity_snapshots (
    opportunity_id TEXT PRIMARY KEY REFERENCES opportunities(id) ON DELETE CASCADE,
    snapshot_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE execution_quality (
    id BIGSERIAL PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    broker_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    expected_price DECIMAL(20, 8) NOT NULL,
    actual_price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    slippage_bps DECIMAL(8, 4) NOT NULL,
    filled_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_execution_quality_agent ON execution_quality(agent_name, filled_at);
CREATE INDEX idx_execution_quality_symbol ON execution_quality(symbol, filled_at);

CREATE TABLE execution_cost_events (
    id BIGSERIAL PRIMARY KEY,
    opportunity_id TEXT,
    tracked_position_id BIGINT,
    order_id TEXT NOT NULL UNIQUE,
    agent_name TEXT,
    symbol TEXT NOT NULL,
    broker_id TEXT,
    account_id TEXT,
    side TEXT NOT NULL,
    order_type TEXT,
    decision_time TIMESTAMPTZ NOT NULL,
    decision_bid DECIMAL(20, 8),
    decision_ask DECIMAL(20, 8),
    decision_last DECIMAL(20, 8),
    decision_price DECIMAL(20, 8),
    fill_time TIMESTAMPTZ,
    fill_price DECIMAL(20, 8),
    filled_quantity DECIMAL(20, 8) NOT NULL,
    fees_total DECIMAL(20, 8) NOT NULL,
    spread_bps DECIMAL(8, 4),
    slippage_bps DECIMAL(8, 4),
    notional DECIMAL(20, 8),
    status TEXT NOT NULL,
    fill_source TEXT NOT NULL DEFAULT 'immediate',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_execution_cost_events_agent ON execution_cost_events(agent_name, decision_time);
CREATE INDEX idx_execution_cost_events_symbol ON execution_cost_events(symbol, decision_time);
CREATE INDEX idx_execution_cost_events_broker ON execution_cost_events(broker_id, decision_time);

CREATE TABLE execution_cost_stats (
    id BIGSERIAL PRIMARY KEY,
    group_type TEXT NOT NULL,
    group_key TEXT NOT NULL,
    window_label TEXT NOT NULL,
    trade_count INTEGER NOT NULL,
    avg_spread_bps DECIMAL(8, 4),
    median_spread_bps DECIMAL(8, 4),
    avg_slippage_bps DECIMAL(8, 4),
    median_slippage_bps DECIMAL(8, 4),
    p95_slippage_bps DECIMAL(8, 4),
    avg_fee_dollars DECIMAL(20, 8) NOT NULL,
    rejection_rate DECIMAL(5, 4),
    partial_fill_rate DECIMAL(5, 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(group_type, group_key, window_label)
);

CREATE INDEX idx_execution_cost_stats_group ON execution_cost_stats(group_type, group_key);

CREATE TABLE trade_analytics (
    tracked_position_id BIGINT PRIMARY KEY REFERENCES tracked_positions(id) ON DELETE CASCADE,
    opportunity_id TEXT,
    agent_name TEXT NOT NULL,
    signal TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    broker_id TEXT,
    account_id TEXT,
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ NOT NULL,
    hold_minutes DECIMAL(10, 2) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    exit_price DECIMAL(20, 8) NOT NULL,
    entry_quantity INTEGER NOT NULL,
    entry_fees DECIMAL(20, 8) NOT NULL,
    exit_fees DECIMAL(20, 8) NOT NULL,
    gross_pnl DECIMAL(20, 8) NOT NULL,
    net_pnl DECIMAL(20, 8) NOT NULL,
    gross_return_pct DECIMAL(8, 4) NOT NULL,
    net_return_pct DECIMAL(8, 4) NOT NULL,
    realized_outcome TEXT NOT NULL,
    exit_reason TEXT,
    confidence DECIMAL(5, 4),
    confidence_bucket TEXT,
    strategy_version TEXT,
    regime_label TEXT,
    trend_regime TEXT,
    volatility_regime TEXT,
    liquidity_regime TEXT,
    execution_slippage_bps DECIMAL(8, 4),
    entry_spread_bps DECIMAL(8, 4),
    order_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trade_analytics_agent ON trade_analytics(agent_name, exit_time);
CREATE INDEX idx_trade_analytics_symbol ON trade_analytics(symbol, agent_name);
CREATE INDEX idx_trade_analytics_regime ON trade_analytics(trend_regime, agent_name);

CREATE TABLE consensus_votes (
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    voted_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (symbol, side, agent_name)
);

CREATE INDEX idx_consensus_votes_window ON consensus_votes(symbol, side, voted_at);

CREATE TABLE whatsapp_sessions (
    phone TEXT PRIMARY KEY,
    last_inbound_at TIMESTAMPTZ NOT NULL
);

-- Agent Management Tables

CREATE TABLE agent_registry (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    strategy TEXT NOT NULL,
    schedule TEXT NOT NULL DEFAULT 'continuous',
    interval_or_cron INTEGER NOT NULL DEFAULT 60,
    universe JSONB NOT NULL DEFAULT '[]',
    parameters JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    trust_level TEXT NOT NULL DEFAULT 'monitored',
    runtime_overrides JSONB NOT NULL DEFAULT '{}',
    promotion_criteria JSONB NOT NULL DEFAULT '{}',
    shadow_mode BOOLEAN NOT NULL DEFAULT FALSE,
    created_by TEXT NOT NULL DEFAULT 'human',
    parent_name TEXT,
    generation INTEGER NOT NULL DEFAULT 1,
    creation_context JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_registry_name_status ON agent_registry(name, status);
CREATE INDEX idx_agent_registry_status ON agent_registry(status);
CREATE INDEX idx_agent_registry_strategy ON agent_registry(strategy);
CREATE INDEX idx_agent_registry_created_by ON agent_registry(created_by);
CREATE INDEX idx_agent_registry_parent ON agent_registry(parent_name);

CREATE TABLE agent_overrides (
    agent_name TEXT PRIMARY KEY,
    trust_level TEXT,
    runtime_parameters JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE trust_events (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    old_level TEXT NOT NULL,
    new_level TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trust_events_agent ON trust_events(agent_name, created_at);

CREATE TABLE agent_stages (
    agent_name TEXT PRIMARY KEY,
    current_stage INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Backtesting & Tournament Tables

CREATE TABLE backtest_results (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    parameters JSONB NOT NULL,
    sharpe_ratio DECIMAL(8, 4),
    profit_factor DECIMAL(8, 4),
    total_pnl DECIMAL(20, 8),
    max_drawdown DECIMAL(8, 4),
    win_rate DECIMAL(5, 4),
    total_trades INTEGER,
    run_date DATE NOT NULL,
    data_start DATE NOT NULL,
    data_end DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_backtest_results_agent ON backtest_results(agent_name, run_date);

CREATE TABLE tournament_rounds (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    champion_params JSONB NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    winner_params JSONB,
    winner_sharpe DECIMAL(8, 4),
    champion_sharpe DECIMAL(8, 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tournament_rounds_agent ON tournament_rounds(agent_name, status);

CREATE TABLE tournament_variants (
    id BIGSERIAL PRIMARY KEY,
    round_id BIGINT NOT NULL REFERENCES tournament_rounds(id) ON DELETE CASCADE,
    variant_label TEXT NOT NULL,
    parameters JSONB NOT NULL,
    sharpe_ratio DECIMAL(8, 4),
    profit_factor DECIMAL(8, 4),
    total_pnl DECIMAL(20, 8),
    total_trades INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tournament_variants_round ON tournament_variants(round_id);

CREATE TABLE tournament_audit_log (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    from_stage INTEGER NOT NULL,
    to_stage INTEGER NOT NULL,
    reason TEXT NOT NULL,
    ai_analysis TEXT NOT NULL DEFAULT '',
    ai_recommendation TEXT NOT NULL DEFAULT '',
    overridden_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tournament_audit_log_agent ON tournament_audit_log(agent_name, created_at);

-- Learning & LLM Tables

CREATE TABLE llm_lessons (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    category TEXT NOT NULL,
    lesson TEXT NOT NULL,
    applies_to TEXT NOT NULL,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_llm_lessons_agent ON llm_lessons(agent_name, archived_at);

CREATE TABLE llm_prompt_versions (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    version INTEGER NOT NULL,
    rules TEXT NOT NULL,
    performance_at_creation JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_llm_prompt_versions_agent ON llm_prompt_versions(agent_name, version);

-- Position Management

CREATE TABLE position_exit_rules (
    position_id BIGINT PRIMARY KEY REFERENCES tracked_positions(id) ON DELETE CASCADE,
    rules_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE trade_autopsies (
    position_id BIGINT PRIMARY KEY REFERENCES tracked_positions(id) ON DELETE CASCADE,
    autopsy_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE daily_briefs (
    date DATE PRIMARY KEY,
    brief_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE convergence_syntheses (
    convergence_id TEXT PRIMARY KEY,
    synthesis_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Shadow Executions

CREATE TABLE shadow_executions (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    action_level TEXT NOT NULL,
    decision_status TEXT NOT NULL,
    expected_entry_price DECIMAL(20, 8),
    expected_quantity DECIMAL(20, 8),
    expected_notional DECIMAL(20, 8),
    entry_price_source TEXT,
    opportunity_snapshot JSONB,
    risk_snapshot JSONB,
    sizing_snapshot JSONB,
    regime_snapshot JSONB,
    health_snapshot JSONB,
    opened_at TIMESTAMPTZ NOT NULL,
    resolve_after TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    resolution_status TEXT NOT NULL DEFAULT 'pending',
    resolution_price DECIMAL(20, 8),
    pnl DECIMAL(20, 8),
    return_bps DECIMAL(8, 4),
    max_favorable_bps DECIMAL(8, 4),
    max_adverse_bps DECIMAL(8, 4),
    resolution_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_shadow_executions_agent ON shadow_executions(agent_name, opened_at);
CREATE INDEX idx_shadow_executions_due ON shadow_executions(resolution_status, resolve_after);
CREATE INDEX idx_shadow_executions_opportunity ON shadow_executions(opportunity_id);
CREATE INDEX idx_shadow_executions_symbol ON shadow_executions(symbol, opened_at);

-- Strategy Health & Calibration

CREATE TABLE strategy_confidence_calibration (
    agent_name TEXT NOT NULL,
    confidence_bucket TEXT NOT NULL,
    window_label TEXT NOT NULL,
    trade_count INTEGER NOT NULL,
    win_rate DECIMAL(5, 4) NOT NULL,
    avg_net_pnl DECIMAL(20, 8) NOT NULL,
    avg_net_return_pct DECIMAL(8, 4) NOT NULL,
    expectancy DECIMAL(20, 8) NOT NULL,
    profit_factor DECIMAL(8, 4),
    max_drawdown DECIMAL(20, 8),
    calibrated_score DECIMAL(8, 4),
    sample_quality TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (agent_name, confidence_bucket, window_label)
);

CREATE INDEX idx_strategy_confidence_calibration_agent ON strategy_confidence_calibration(agent_name, window_label);

CREATE TABLE strategy_health (
    agent_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    health_score DECIMAL(5, 4),
    rolling_expectancy DECIMAL(20, 8),
    rolling_net_pnl DECIMAL(20, 8),
    rolling_drawdown DECIMAL(20, 8),
    rolling_win_rate DECIMAL(5, 4),
    rolling_trade_count INTEGER NOT NULL DEFAULT 0,
    throttle_multiplier DECIMAL(5, 2),
    trigger_reason TEXT,
    cooldown_until TIMESTAMPTZ,
    manual_override TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_strategy_health_status ON strategy_health(status);

CREATE TABLE strategy_health_events (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    metrics_snapshot JSONB NOT NULL DEFAULT '{}',
    actor TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_strategy_health_events_agent ON strategy_health_events(agent_name, created_at);

-- Signal Features (ML)

CREATE TABLE signal_features (
    opportunity_id TEXT PRIMARY KEY REFERENCES opportunities(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    signal TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT 'STOCK',
    broker_id TEXT,
    confidence DECIMAL(5, 4) NOT NULL,
    opportunity_timestamp TIMESTAMPTZ NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    capture_delay_ms DECIMAL(10, 2),
    feature_version TEXT NOT NULL DEFAULT '1.0',
    quote_bid DECIMAL(20, 8),
    quote_ask DECIMAL(20, 8),
    quote_last DECIMAL(20, 8),
    quote_mid DECIMAL(20, 8),
    spread_bps DECIMAL(8, 4),
    rsi_14 DECIMAL(8, 4),
    sma_20 DECIMAL(20, 8),
    ema_20 DECIMAL(20, 8),
    macd_line DECIMAL(20, 8),
    macd_signal DECIMAL(20, 8),
    macd_histogram DECIMAL(20, 8),
    bollinger_upper DECIMAL(20, 8),
    bollinger_middle DECIMAL(20, 8),
    bollinger_lower DECIMAL(20, 8),
    bollinger_pct_b DECIMAL(8, 4),
    atr_14 DECIMAL(20, 8),
    realized_vol_20d DECIMAL(8, 4),
    relative_volume_20d DECIMAL(8, 4),
    distance_to_sma20_pct DECIMAL(8, 4),
    distance_to_ema20_pct DECIMAL(8, 4),
    trend_regime TEXT,
    volatility_regime TEXT,
    liquidity_regime TEXT,
    event_regime TEXT,
    market_state TEXT,
    market_proxy_symbol TEXT,
    market_proxy_rsi_14 DECIMAL(8, 4),
    market_proxy_return_1d DECIMAL(8, 4),
    feature_payload JSONB NOT NULL DEFAULT '{}',
    capture_status TEXT NOT NULL DEFAULT 'captured',
    capture_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signal_features_agent ON signal_features(agent_name, opportunity_timestamp);
CREATE INDEX idx_signal_features_symbol ON signal_features(symbol, opportunity_timestamp);
CREATE INDEX idx_signal_features_signal ON signal_features(signal, agent_name);

-- Leaderboard & Agent Maps

CREATE TABLE leaderboard_cache (
    id BIGSERIAL PRIMARY KEY CHECK (id = 1),
    rankings_json JSONB NOT NULL,
    last_processed_snapshot_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL DEFAULT 'live',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE agent_remembr_map (
    agent_name TEXT PRIMARY KEY,
    remembr_agent_id TEXT NOT NULL,
    remembr_token TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Arbitrage Tables

CREATE TABLE arb_spread_observations (
    id BIGSERIAL PRIMARY KEY,
    kalshi_ticker TEXT NOT NULL,
    poly_ticker TEXT NOT NULL,
    match_score DECIMAL(5, 4) NOT NULL,
    kalshi_cents INTEGER NOT NULL,
    poly_cents INTEGER NOT NULL,
    gap_cents INTEGER NOT NULL,
    kalshi_volume DECIMAL(20, 8) NOT NULL DEFAULT 0,
    poly_volume DECIMAL(20, 8) NOT NULL DEFAULT 0,
    is_claimed BOOLEAN NOT NULL DEFAULT FALSE,
    claimed_at TIMESTAMPTZ,
    claimed_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_arb_spread_observations_pair ON arb_spread_observations(kalshi_ticker, poly_ticker, created_at);
CREATE INDEX idx_arb_spread_observations_gap ON arb_spread_observations(gap_cents, created_at);

CREATE TABLE arb_trades (
    id TEXT PRIMARY KEY,
    symbol_a TEXT NOT NULL,
    symbol_b TEXT NOT NULL,
    expected_profit_bps INTEGER NOT NULL,
    sequencing TEXT NOT NULL,
    state TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_arb_trades_state ON arb_trades(state);

CREATE TABLE arb_legs (
    trade_id TEXT NOT NULL REFERENCES arb_trades(id) ON DELETE CASCADE,
    leg_name TEXT NOT NULL,
    broker_id TEXT NOT NULL,
    order_data JSONB NOT NULL,
    fill_price DECIMAL(20, 8),
    fill_quantity DECIMAL(20, 8) NOT NULL,
    status TEXT NOT NULL,
    external_order_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_id, leg_name)
);

CREATE INDEX idx_arb_legs_trade ON arb_legs(trade_id);

-- Bittensor Tables

CREATE TABLE bittensor_raw_forecasts (
    id BIGSERIAL PRIMARY KEY,
    window_id TEXT NOT NULL,
    request_uuid TEXT NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    stream_id TEXT NOT NULL,
    topic_id INTEGER NOT NULL,
    schema_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    feature_ids TEXT NOT NULL,
    prediction_size INTEGER NOT NULL,
    miner_uid INTEGER,
    miner_hotkey TEXT NOT NULL,
    predictions TEXT NOT NULL,
    hashed_predictions TEXT,
    hash_verified BOOLEAN NOT NULL DEFAULT FALSE,
    incentive_score DECIMAL(8, 6),
    vtrust DECIMAL(8, 6),
    stake_tao DECIMAL(20, 8),
    metagraph_block BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(window_id, miner_hotkey, request_uuid)
);

CREATE INDEX idx_bittensor_raw_forecasts_window ON bittensor_raw_forecasts(window_id);
CREATE INDEX idx_bittensor_raw_forecasts_symbol ON bittensor_raw_forecasts(symbol, timeframe, collected_at);
CREATE INDEX idx_bittensor_raw_forecasts_miner ON bittensor_raw_forecasts(miner_hotkey, collected_at);

CREATE TABLE bittensor_derived_views (
    window_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    responder_count INTEGER NOT NULL,
    bullish_count INTEGER NOT NULL,
    bearish_count INTEGER NOT NULL,
    flat_count INTEGER NOT NULL,
    weighted_direction DECIMAL(8, 4) NOT NULL,
    weighted_expected_return DECIMAL(8, 4) NOT NULL,
    agreement_ratio DECIMAL(5, 4) NOT NULL,
    equal_weight_direction DECIMAL(8, 4) NOT NULL,
    equal_weight_expected_return DECIMAL(8, 4) NOT NULL,
    is_low_confidence BOOLEAN NOT NULL DEFAULT FALSE,
    derivation_version TEXT NOT NULL,
    evaluation_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bittensor_derived_views_symbol ON bittensor_derived_views(symbol, timeframe, timestamp);

CREATE TABLE bittensor_realized_windows (
    window_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    realized_path TEXT NOT NULL,
    realized_return DECIMAL(8, 4) NOT NULL,
    bars_used INTEGER NOT NULL,
    source TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bittensor_realized_windows_symbol ON bittensor_realized_windows(symbol, timeframe, captured_at);

CREATE TABLE bittensor_accuracy_records (
    id BIGSERIAL PRIMARY KEY,
    window_id TEXT NOT NULL,
    miner_hotkey TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction_correct BOOLEAN NOT NULL,
    predicted_return DECIMAL(8, 4) NOT NULL,
    actual_return DECIMAL(8, 4) NOT NULL,
    magnitude_error DECIMAL(8, 4) NOT NULL,
    path_correlation DECIMAL(8, 6),
    outcome_bars INTEGER NOT NULL,
    scoring_version TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(window_id, miner_hotkey)
);

CREATE INDEX idx_bittensor_accuracy_records_miner ON bittensor_accuracy_records(miner_hotkey, evaluated_at);
CREATE INDEX idx_bittensor_accuracy_records_window ON bittensor_accuracy_records(window_id, miner_hotkey);
CREATE INDEX idx_bittensor_accuracy_records_symbol ON bittensor_accuracy_records(symbol, timeframe, evaluated_at);

CREATE TABLE bittensor_miner_rankings (
    miner_hotkey TEXT PRIMARY KEY,
    windows_evaluated INTEGER NOT NULL,
    direction_accuracy DECIMAL(5, 4) NOT NULL,
    mean_magnitude_error DECIMAL(8, 4) NOT NULL,
    mean_path_correlation DECIMAL(8, 6),
    internal_score DECIMAL(8, 4) NOT NULL,
    latest_incentive_score DECIMAL(8, 6),
    hybrid_score DECIMAL(8, 4) NOT NULL,
    alpha_used DECIMAL(5, 4) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bittensor_miner_rankings_hybrid ON bittensor_miner_rankings(hybrid_score DESC);
CREATE INDEX idx_bittensor_miner_rankings_internal ON bittensor_miner_rankings(internal_score DESC);
