-- =============================================================================
-- PostgreSQL CREATE TABLE script for trading service
-- Generated from Laravel migrations (2026_04_05_000001/2/3)
-- =============================================================================

-- Core Trading Tables
CREATE TABLE IF NOT EXISTS opportunities (
    id VARCHAR(255) PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    symbol VARCHAR(255) NOT NULL,
    signal VARCHAR(255) NOT NULL,
    confidence DECIMAL(8,4) NOT NULL,
    reasoning TEXT NOT NULL,
    suggested_trade TEXT NULL,
    status VARCHAR(255) NOT NULL DEFAULT 'pending',
    expires_at TIMESTAMP NULL,
    data JSONB NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities (status);
CREATE INDEX IF NOT EXISTS idx_opportunities_agent_created ON opportunities (agent_name, created_at);
CREATE INDEX IF NOT EXISTS idx_opportunities_symbol_created ON opportunities (symbol, created_at);

CREATE TABLE IF NOT EXISTS trade_executions (
    id BIGSERIAL PRIMARY KEY,
    opportunity_id VARCHAR(255) NULL,
    agent_name VARCHAR(255) NULL,
    order_result JSONB NOT NULL,
    risk_evaluation JSONB NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_executions_opp_created ON trade_executions (opportunity_id, created_at);
CREATE INDEX IF NOT EXISTS idx_trade_executions_agent_created ON trade_executions (agent_name, created_at);

CREATE TABLE IF NOT EXISTS tracked_positions (
    id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    opportunity_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(255) NOT NULL,
    side VARCHAR(255) NOT NULL,
    entry_price DECIMAL(20,8) NOT NULL,
    entry_quantity INTEGER NOT NULL,
    entry_fees DECIMAL(20,8) NOT NULL DEFAULT 0,
    entry_time TIMESTAMP NOT NULL,
    exit_price DECIMAL(20,8) NULL,
    exit_fees DECIMAL(20,8) NULL,
    exit_time TIMESTAMP NULL,
    exit_reason VARCHAR(255) NULL,
    max_adverse_excursion DECIMAL(20,8) NOT NULL DEFAULT 0,
    status VARCHAR(255) NOT NULL DEFAULT 'open',
    expires_at TIMESTAMP NULL,
    broker_id VARCHAR(255) NULL,
    account_id VARCHAR(255) NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_tracked_positions_status ON tracked_positions (status);
CREATE INDEX IF NOT EXISTS idx_tracked_positions_agent_status_created ON tracked_positions (agent_name, status, created_at);
CREATE INDEX IF NOT EXISTS idx_tracked_positions_symbol_status_created ON tracked_positions (symbol, status, created_at);

CREATE TABLE IF NOT EXISTS external_positions (
    id BIGSERIAL PRIMARY KEY,
    broker VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    account_name VARCHAR(255) NOT NULL DEFAULT '',
    symbol VARCHAR(255) NOT NULL,
    description VARCHAR(255) NOT NULL DEFAULT '',
    quantity DECIMAL(20,8) NOT NULL,
    cost_basis DECIMAL(20,8) NULL,
    current_value DECIMAL(20,8) NOT NULL,
    last_price DECIMAL(20,8) NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_external_positions_broker_imported ON external_positions (broker, imported_at);
CREATE INDEX IF NOT EXISTS idx_external_positions_symbol_imported ON external_positions (symbol, imported_at);

CREATE TABLE IF NOT EXISTS external_balances (
    id BIGSERIAL PRIMARY KEY,
    broker VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    account_name VARCHAR(255) NOT NULL DEFAULT '',
    net_liquidation DECIMAL(20,8) NOT NULL,
    cash DECIMAL(20,8) NOT NULL DEFAULT 0,
    imported_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_external_balances_broker_imported ON external_balances (broker, imported_at);

CREATE TABLE IF NOT EXISTS risk_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(255) NOT NULL,
    details TEXT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_risk_events_type_created ON risk_events (event_type, created_at);

CREATE TABLE IF NOT EXISTS performance_snapshots (
    id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    opportunities_generated INTEGER NOT NULL,
    opportunities_executed INTEGER NOT NULL,
    win_rate DECIMAL(5,4) NOT NULL,
    total_pnl DECIMAL(20,8) NULL,
    daily_pnl DECIMAL(20,8) NULL,
    daily_pnl_pct DECIMAL(8,4) NULL,
    sharpe_ratio DECIMAL(8,4) NULL,
    max_drawdown DECIMAL(8,4) NULL,
    avg_win DECIMAL(20,8) NULL,
    avg_loss DECIMAL(20,8) NULL,
    profit_factor DECIMAL(8,4) NULL,
    total_trades INTEGER NULL,
    open_positions INTEGER NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_performance_snapshots_agent_created ON performance_snapshots (agent_name, created_at);

CREATE TABLE IF NOT EXISTS opportunity_snapshots (
    opportunity_id VARCHAR(255) PRIMARY KEY,
    snapshot_data JSONB NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS execution_quality (
    id BIGSERIAL PRIMARY KEY,
    opportunity_id VARCHAR(255) NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    broker_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(255) NOT NULL,
    side VARCHAR(255) NOT NULL,
    expected_price DECIMAL(20,8) NOT NULL,
    actual_price DECIMAL(20,8) NOT NULL,
    quantity DECIMAL(20,8) NOT NULL,
    slippage_bps DECIMAL(8,4) NOT NULL,
    filled_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_execution_quality_agent_filled ON execution_quality (agent_name, filled_at);
CREATE INDEX IF NOT EXISTS idx_execution_quality_symbol_filled ON execution_quality (symbol, filled_at);

CREATE TABLE IF NOT EXISTS execution_cost_events (
    id BIGSERIAL PRIMARY KEY,
    opportunity_id VARCHAR(255) NULL,
    tracked_position_id BIGINT NULL,
    order_id VARCHAR(255) NOT NULL UNIQUE,
    agent_name VARCHAR(255) NULL,
    symbol VARCHAR(255) NOT NULL,
    broker_id VARCHAR(255) NULL,
    account_id VARCHAR(255) NULL,
    side VARCHAR(255) NOT NULL,
    order_type VARCHAR(255) NULL,
    decision_time TIMESTAMP NOT NULL,
    decision_bid DECIMAL(20,8) NULL,
    decision_ask DECIMAL(20,8) NULL,
    decision_last DECIMAL(20,8) NULL,
    decision_price DECIMAL(20,8) NULL,
    fill_time TIMESTAMP NULL,
    fill_price DECIMAL(20,8) NULL,
    filled_quantity DECIMAL(20,8) NOT NULL,
    fees_total DECIMAL(20,8) NOT NULL,
    spread_bps DECIMAL(8,4) NULL,
    slippage_bps DECIMAL(8,4) NULL,
    notional DECIMAL(20,8) NULL,
    status VARCHAR(255) NOT NULL,
    fill_source VARCHAR(255) NOT NULL DEFAULT 'immediate',
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_exec_cost_events_agent_decision ON execution_cost_events (agent_name, decision_time);
CREATE INDEX IF NOT EXISTS idx_exec_cost_events_symbol_decision ON execution_cost_events (symbol, decision_time);
CREATE INDEX IF NOT EXISTS idx_exec_cost_events_broker_decision ON execution_cost_events (broker_id, decision_time);

CREATE TABLE IF NOT EXISTS execution_cost_stats (
    id BIGSERIAL PRIMARY KEY,
    group_type VARCHAR(255) NOT NULL,
    group_key VARCHAR(255) NOT NULL,
    window_label VARCHAR(255) NOT NULL,
    trade_count INTEGER NOT NULL,
    avg_spread_bps DECIMAL(8,4) NULL,
    median_spread_bps DECIMAL(8,4) NULL,
    avg_slippage_bps DECIMAL(8,4) NULL,
    median_slippage_bps DECIMAL(8,4) NULL,
    p95_slippage_bps DECIMAL(8,4) NULL,
    avg_fee_dollars DECIMAL(20,8) NOT NULL,
    rejection_rate DECIMAL(5,4) NULL,
    partial_fill_rate DECIMAL(5,4) NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    UNIQUE (group_type, group_key, window_label)
);
CREATE INDEX IF NOT EXISTS idx_exec_cost_stats_group ON execution_cost_stats (group_type, group_key);

CREATE TABLE IF NOT EXISTS trade_analytics (
    tracked_position_id BIGINT PRIMARY KEY,
    opportunity_id VARCHAR(255) NULL,
    agent_name VARCHAR(255) NOT NULL,
    signal VARCHAR(255) NULL,
    symbol VARCHAR(255) NOT NULL,
    side VARCHAR(255) NOT NULL,
    broker_id VARCHAR(255) NULL,
    account_id VARCHAR(255) NULL,
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP NOT NULL,
    hold_minutes DECIMAL(10,2) NOT NULL,
    entry_price DECIMAL(20,8) NOT NULL,
    exit_price DECIMAL(20,8) NOT NULL,
    entry_quantity INTEGER NOT NULL,
    entry_fees DECIMAL(20,8) NOT NULL,
    exit_fees DECIMAL(20,8) NOT NULL,
    gross_pnl DECIMAL(20,8) NOT NULL,
    net_pnl DECIMAL(20,8) NOT NULL,
    gross_return_pct DECIMAL(8,4) NOT NULL,
    net_return_pct DECIMAL(8,4) NOT NULL,
    realized_outcome VARCHAR(255) NOT NULL,
    exit_reason VARCHAR(255) NULL,
    confidence DECIMAL(5,4) NULL,
    confidence_bucket VARCHAR(255) NULL,
    strategy_version VARCHAR(255) NULL,
    regime_label VARCHAR(255) NULL,
    trend_regime VARCHAR(255) NULL,
    volatility_regime VARCHAR(255) NULL,
    liquidity_regime VARCHAR(255) NULL,
    execution_slippage_bps DECIMAL(8,4) NULL,
    entry_spread_bps DECIMAL(8,4) NULL,
    order_type VARCHAR(255) NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_analytics_agent_exit ON trade_analytics (agent_name, exit_time);
CREATE INDEX IF NOT EXISTS idx_trade_analytics_symbol_agent ON trade_analytics (symbol, agent_name);
CREATE INDEX IF NOT EXISTS idx_trade_analytics_trend_agent ON trade_analytics (trend_regime, agent_name);

CREATE TABLE IF NOT EXISTS consensus_votes (
    symbol VARCHAR(255) NOT NULL,
    side VARCHAR(255) NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    opportunity_id VARCHAR(255) NOT NULL,
    voted_at TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, side, agent_name)
);
CREATE INDEX IF NOT EXISTS idx_consensus_votes_symbol_side_voted ON consensus_votes (symbol, side, voted_at);

CREATE TABLE IF NOT EXISTS whatsapp_sessions (
    phone VARCHAR(255) PRIMARY KEY,
    last_inbound_at TIMESTAMP NOT NULL
);

-- Extended Trading Tables
CREATE TABLE IF NOT EXISTS agent_registry (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    strategy VARCHAR(255) NOT NULL,
    schedule VARCHAR(255) NOT NULL DEFAULT 'continuous',
    interval_or_cron INTEGER NOT NULL DEFAULT 60,
    universe JSONB NOT NULL DEFAULT '[]',
    parameters JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(255) NOT NULL DEFAULT 'active',
    trust_level VARCHAR(255) NOT NULL DEFAULT 'monitored',
    runtime_overrides JSONB NOT NULL DEFAULT '{}',
    promotion_criteria JSONB NOT NULL DEFAULT '{}',
    shadow_mode BOOLEAN NOT NULL DEFAULT false,
    created_by VARCHAR(255) NOT NULL DEFAULT 'human',
    parent_name VARCHAR(255) NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    creation_context JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_registry_status ON agent_registry (status);
CREATE INDEX IF NOT EXISTS idx_agent_registry_name_status ON agent_registry (name, status);

CREATE TABLE IF NOT EXISTS agent_overrides (
    agent_name VARCHAR(255) PRIMARY KEY,
    trust_level VARCHAR(255) NULL,
    runtime_parameters JSONB NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS trust_events (
    id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    old_level VARCHAR(255) NOT NULL,
    new_level VARCHAR(255) NOT NULL,
    changed_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS agent_stages (
    agent_name VARCHAR(255) PRIMARY KEY,
    current_stage INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS agent_elo_ratings (
    agent_name VARCHAR(255) PRIMARY KEY,
    elo_rating INTEGER NOT NULL DEFAULT 1000,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS elo_rating_history (
    id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    old_rating INTEGER NOT NULL,
    new_rating INTEGER NOT NULL,
    reason VARCHAR(500) NULL,
    delta INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_elo_history_agent ON elo_rating_history(agent_name);
CREATE INDEX idx_elo_history_timestamp ON elo_rating_history(timestamp);

CREATE TABLE IF NOT EXISTS backtest_results (
    id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    parameters JSONB NOT NULL,
    sharpe_ratio DECIMAL(8,4) NULL,
    profit_factor DECIMAL(8,4) NULL,
    total_pnl DECIMAL(20,8) NULL,
    max_drawdown DECIMAL(8,4) NULL,
    win_rate DECIMAL(5,4) NULL,
    total_trades INTEGER NULL,
    run_date DATE NOT NULL,
    data_start DATE NOT NULL,
    data_end DATE NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS tournament_rounds (
    id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    status VARCHAR(255) NOT NULL DEFAULT 'running',
    champion_params JSONB NOT NULL,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP NULL,
    winner_params JSONB NULL,
    winner_sharpe DECIMAL(8,4) NULL,
    champion_sharpe DECIMAL(8,4) NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS tournament_variants (
    id BIGSERIAL PRIMARY KEY,
    round_id BIGINT NOT NULL,
    variant_label VARCHAR(255) NOT NULL,
    parameters JSONB NOT NULL,
    sharpe_ratio DECIMAL(8,4) NULL,
    profit_factor DECIMAL(8,4) NULL,
    total_pnl DECIMAL(20,8) NULL,
    total_trades INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS tournament_audit_log (
    id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    from_stage INTEGER NOT NULL,
    to_stage INTEGER NOT NULL,
    reason TEXT NOT NULL,
    ai_analysis TEXT NOT NULL DEFAULT '',
    ai_recommendation TEXT NOT NULL DEFAULT '',
    overridden_by VARCHAR(255) NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS llm_lessons (
    id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    opportunity_id VARCHAR(255) NOT NULL,
    category VARCHAR(255) NOT NULL,
    lesson TEXT NOT NULL,
    applies_to VARCHAR(255) NOT NULL,
    archived_at TIMESTAMP NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS llm_prompt_versions (
    id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    version INTEGER NOT NULL,
    rules TEXT NOT NULL,
    performance_at_creation JSONB NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS position_exit_rules (
    position_id BIGINT PRIMARY KEY,
    rules_json JSONB NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS trade_autopsies (
    position_id BIGINT PRIMARY KEY,
    autopsy_text TEXT NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS daily_briefs (
    date DATE PRIMARY KEY,
    brief_text TEXT NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS convergence_syntheses (
    convergence_id VARCHAR(255) PRIMARY KEY,
    synthesis_text TEXT NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS shadow_executions (
    id VARCHAR(255) PRIMARY KEY,
    opportunity_id VARCHAR(255) NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    symbol VARCHAR(255) NOT NULL,
    side VARCHAR(255) NOT NULL,
    action_level VARCHAR(255) NOT NULL,
    decision_status VARCHAR(255) NOT NULL,
    expected_entry_price DECIMAL(20,8) NULL,
    expected_quantity DECIMAL(20,8) NULL,
    expected_notional DECIMAL(20,8) NULL,
    entry_price_source VARCHAR(255) NULL,
    opportunity_snapshot JSONB NULL,
    risk_snapshot JSONB NULL,
    sizing_snapshot JSONB NULL,
    regime_snapshot JSONB NULL,
    health_snapshot JSONB NULL,
    opened_at TIMESTAMP NOT NULL,
    resolve_after TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP NULL,
    resolution_status VARCHAR(255) NOT NULL DEFAULT 'pending',
    resolution_price DECIMAL(20,8) NULL,
    pnl DECIMAL(20,8) NULL,
    return_bps DECIMAL(8,4) NULL,
    max_favorable_bps DECIMAL(8,4) NULL,
    max_adverse_bps DECIMAL(8,4) NULL,
    resolution_notes TEXT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_exec_agent_opened ON shadow_executions (agent_name, opened_at);
CREATE INDEX IF NOT EXISTS idx_shadow_exec_resolution_resolve ON shadow_executions (resolution_status, resolve_after);

CREATE TABLE IF NOT EXISTS strategy_confidence_calibration (
    agent_name VARCHAR(255) NOT NULL,
    confidence_bucket VARCHAR(255) NOT NULL,
    window_label VARCHAR(255) NOT NULL,
    trade_count INTEGER NOT NULL,
    win_rate DECIMAL(5,4) NOT NULL,
    avg_net_pnl DECIMAL(20,8) NOT NULL,
    avg_net_return_pct DECIMAL(8,4) NOT NULL,
    expectancy DECIMAL(20,8) NOT NULL,
    profit_factor DECIMAL(8,4) NULL,
    max_drawdown DECIMAL(20,8) NULL,
    calibrated_score DECIMAL(8,4) NULL,
    sample_quality VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    PRIMARY KEY (agent_name, confidence_bucket, window_label)
);

CREATE TABLE IF NOT EXISTS strategy_health (
    agent_name VARCHAR(255) PRIMARY KEY,
    status VARCHAR(255) NOT NULL,
    health_score DECIMAL(5,4) NULL,
    rolling_expectancy DECIMAL(20,8) NULL,
    rolling_net_pnl DECIMAL(20,8) NULL,
    rolling_drawdown DECIMAL(20,8) NULL,
    rolling_win_rate DECIMAL(5,4) NULL,
    rolling_trade_count INTEGER NOT NULL DEFAULT 0,
    throttle_multiplier DECIMAL(5,2) NULL,
    trigger_reason VARCHAR(255) NULL,
    cooldown_until TIMESTAMP NULL,
    manual_override VARCHAR(255) NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS strategy_health_events (
    id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    old_status VARCHAR(255) NULL,
    new_status VARCHAR(255) NOT NULL,
    reason TEXT NOT NULL,
    metrics_snapshot JSONB NOT NULL DEFAULT '{}',
    actor VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS signal_features (
    opportunity_id VARCHAR(255) PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    symbol VARCHAR(255) NOT NULL,
    signal VARCHAR(255) NOT NULL,
    asset_type VARCHAR(255) NOT NULL DEFAULT 'STOCK',
    broker_id VARCHAR(255) NULL,
    confidence DECIMAL(5,4) NOT NULL,
    opportunity_timestamp TIMESTAMP NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    capture_delay_ms DECIMAL(10,2) NULL,
    feature_version VARCHAR(255) NOT NULL DEFAULT '1.0',
    quote_bid DECIMAL(20,8) NULL,
    quote_ask DECIMAL(20,8) NULL,
    quote_last DECIMAL(20,8) NULL,
    quote_mid DECIMAL(20,8) NULL,
    spread_bps DECIMAL(8,4) NULL,
    rsi_14 DECIMAL(8,4) NULL,
    sma_20 DECIMAL(20,8) NULL,
    ema_20 DECIMAL(20,8) NULL,
    macd_line DECIMAL(20,8) NULL,
    macd_signal DECIMAL(20,8) NULL,
    macd_histogram DECIMAL(20,8) NULL,
    bollinger_upper DECIMAL(20,8) NULL,
    bollinger_middle DECIMAL(20,8) NULL,
    bollinger_lower DECIMAL(20,8) NULL,
    bollinger_pct_b DECIMAL(8,4) NULL,
    atr_14 DECIMAL(20,8) NULL,
    realized_vol_20d DECIMAL(8,4) NULL,
    relative_volume_20d DECIMAL(8,4) NULL,
    distance_to_sma20_pct DECIMAL(8,4) NULL,
    distance_to_ema20_pct DECIMAL(8,4) NULL,
    trend_regime VARCHAR(255) NULL,
    volatility_regime VARCHAR(255) NULL,
    liquidity_regime VARCHAR(255) NULL,
    event_regime VARCHAR(255) NULL,
    market_state VARCHAR(255) NULL,
    market_proxy_symbol VARCHAR(255) NULL,
    market_proxy_rsi_14 DECIMAL(8,4) NULL,
    market_proxy_return_1d DECIMAL(8,4) NULL,
    feature_payload JSONB NOT NULL DEFAULT '{}',
    capture_status VARCHAR(255) NOT NULL DEFAULT 'captured',
    capture_error TEXT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS leaderboard_cache (
    id BIGSERIAL PRIMARY KEY,
    rankings_json JSONB NOT NULL,
    last_processed_snapshot_at TIMESTAMP NOT NULL,
    source VARCHAR(255) NOT NULL DEFAULT 'live',
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS agent_remembr_map (
    agent_name VARCHAR(255) PRIMARY KEY,
    remembr_agent_id VARCHAR(255) NOT NULL,
    remembr_token VARCHAR(255) NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

-- Bittensor Tables
CREATE TABLE IF NOT EXISTS bittensor_raw_forecasts (
    id BIGSERIAL PRIMARY KEY,
    window_id VARCHAR(255) NOT NULL,
    request_uuid VARCHAR(255) NOT NULL,
    collected_at TIMESTAMP NOT NULL,
    stream_id VARCHAR(255) NOT NULL,
    topic_id INTEGER NOT NULL,
    schema_id INTEGER NOT NULL,
    symbol VARCHAR(255) NOT NULL,
    timeframe VARCHAR(255) NOT NULL,
    feature_ids VARCHAR(255) NOT NULL,
    prediction_size INTEGER NOT NULL,
    miner_uid INTEGER NULL,
    miner_hotkey VARCHAR(255) NOT NULL,
    predictions TEXT NOT NULL,
    hashed_predictions VARCHAR(255) NULL,
    hash_verified BOOLEAN NOT NULL DEFAULT false,
    incentive_score DECIMAL(8,6) NULL,
    vtrust DECIMAL(8,6) NULL,
    stake_tao DECIMAL(20,8) NULL,
    metagraph_block BIGINT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    UNIQUE (window_id, miner_hotkey, request_uuid)
);
CREATE INDEX IF NOT EXISTS idx_bt_raw_window ON bittensor_raw_forecasts (window_id);
CREATE INDEX IF NOT EXISTS idx_bt_raw_symbol_tf_collected ON bittensor_raw_forecasts (symbol, timeframe, collected_at);

CREATE TABLE IF NOT EXISTS bittensor_derived_views (
    window_id VARCHAR(255) PRIMARY KEY,
    symbol VARCHAR(255) NOT NULL,
    timeframe VARCHAR(255) NOT NULL,
    "timestamp" TIMESTAMP NOT NULL,
    responder_count INTEGER NOT NULL,
    bullish_count INTEGER NOT NULL,
    bearish_count INTEGER NOT NULL,
    flat_count INTEGER NOT NULL,
    weighted_direction DECIMAL(8,4) NOT NULL,
    weighted_expected_return DECIMAL(8,4) NOT NULL,
    agreement_ratio DECIMAL(5,4) NOT NULL,
    equal_weight_direction DECIMAL(8,4) NOT NULL,
    equal_weight_expected_return DECIMAL(8,4) NOT NULL,
    is_low_confidence BOOLEAN NOT NULL DEFAULT false,
    derivation_version VARCHAR(255) NOT NULL,
    evaluation_status VARCHAR(255) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_bt_derived_symbol_tf_ts ON bittensor_derived_views (symbol, timeframe, "timestamp");

CREATE TABLE IF NOT EXISTS bittensor_realized_windows (
    window_id VARCHAR(255) PRIMARY KEY,
    symbol VARCHAR(255) NOT NULL,
    timeframe VARCHAR(255) NOT NULL,
    realized_path TEXT NOT NULL,
    realized_return DECIMAL(8,4) NOT NULL,
    bars_used INTEGER NOT NULL,
    source VARCHAR(255) NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS bittensor_accuracy_records (
    id BIGSERIAL PRIMARY KEY,
    window_id VARCHAR(255) NOT NULL,
    miner_hotkey VARCHAR(255) NOT NULL,
    symbol VARCHAR(255) NOT NULL,
    timeframe VARCHAR(255) NOT NULL,
    direction_correct BOOLEAN NOT NULL,
    predicted_return DECIMAL(8,4) NOT NULL,
    actual_return DECIMAL(8,4) NOT NULL,
    magnitude_error DECIMAL(8,4) NOT NULL,
    path_correlation DECIMAL(8,6) NULL,
    outcome_bars INTEGER NOT NULL,
    scoring_version VARCHAR(255) NOT NULL,
    evaluated_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    UNIQUE (window_id, miner_hotkey)
);

CREATE TABLE IF NOT EXISTS bittensor_miner_rankings (
    miner_hotkey VARCHAR(255) PRIMARY KEY,
    windows_evaluated INTEGER NOT NULL,
    direction_accuracy DECIMAL(5,4) NOT NULL,
    mean_magnitude_error DECIMAL(8,4) NOT NULL,
    mean_path_correlation DECIMAL(8,6) NULL,
    internal_score DECIMAL(8,4) NOT NULL,
    latest_incentive_score DECIMAL(8,6) NULL,
    hybrid_score DECIMAL(8,4) NOT NULL,
    alpha_used DECIMAL(5,4) NOT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

-- Arbitrage Tables
CREATE TABLE IF NOT EXISTS arb_spread_observations (
    id BIGSERIAL PRIMARY KEY,
    kalshi_ticker VARCHAR(255) NOT NULL,
    poly_ticker VARCHAR(255) NOT NULL,
    match_score DECIMAL(5,4) NOT NULL,
    kalshi_cents INTEGER NOT NULL,
    poly_cents INTEGER NOT NULL,
    gap_cents INTEGER NOT NULL,
    kalshi_volume DECIMAL(20,8) NOT NULL DEFAULT 0,
    poly_volume DECIMAL(20,8) NOT NULL DEFAULT 0,
    is_claimed BOOLEAN NOT NULL DEFAULT false,
    claimed_at TIMESTAMP NULL,
    claimed_by VARCHAR(255) NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS arb_trades (
    id VARCHAR(255) PRIMARY KEY,
    symbol_a VARCHAR(255) NOT NULL,
    symbol_b VARCHAR(255) NOT NULL,
    expected_profit_bps INTEGER NOT NULL,
    sequencing VARCHAR(255) NOT NULL,
    state VARCHAR(255) NOT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS arb_legs (
    trade_id VARCHAR(255) NOT NULL,
    leg_name VARCHAR(255) NOT NULL,
    broker_id VARCHAR(255) NOT NULL,
    order_data JSONB NOT NULL,
    fill_price DECIMAL(20,8) NULL,
    fill_quantity DECIMAL(20,8) NOT NULL,
    status VARCHAR(255) NOT NULL,
    external_order_id VARCHAR(255) NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    PRIMARY KEY (trade_id, leg_name)
);

-- Paper trading tables (needed for paper mode)
-- Paper trading tables — schema must match trading/storage/paper.py
CREATE TABLE IF NOT EXISTS paper_accounts (
    account_id TEXT PRIMARY KEY,
    net_liquidation REAL NOT NULL,
    buying_power REAL NOT NULL,
    cash REAL NOT NULL,
    maintenance_margin REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_positions (
    account_id TEXT,
    symbol TEXT,
    asset_type TEXT,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0.0,
    resolved_at TEXT,
    PRIMARY KEY (account_id, symbol, asset_type)
);

CREATE TABLE IF NOT EXISTS paper_orders (
    order_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    status TEXT NOT NULL,
    filled_quantity REAL NOT NULL,
    avg_fill_price REAL,
    created_at TEXT NOT NULL DEFAULT (NOW()::TEXT)
);

CREATE TABLE IF NOT EXISTS correlation_matrix (
    symbol_a VARCHAR(255) NOT NULL,
    symbol_b VARCHAR(255) NOT NULL,
    correlation DECIMAL(8,6) NOT NULL,
    window_days INTEGER NOT NULL DEFAULT 30,
    computed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol_a, symbol_b, window_days)
);

CREATE TABLE IF NOT EXISTS bittensor_processed_positions (
    position_uuid VARCHAR(255) PRIMARY KEY,
    miner_hotkey VARCHAR(255) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bt_processed_hotkey ON bittensor_processed_positions(miner_hotkey);

-- Agent context cache (used by prompt_store for LLM agent prompts)
CREATE TABLE IF NOT EXISTS agent_context_cache (
    agent_name TEXT PRIMARY KEY,
    l0_text TEXT NOT NULL,
    l1_text TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    trade_count INTEGER DEFAULT 0
);

