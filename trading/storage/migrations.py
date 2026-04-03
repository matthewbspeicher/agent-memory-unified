from __future__ import annotations

"""PostgreSQL schema migrations.

Translates the SQLite CREATE TABLE / CREATE INDEX statements from db.py into
their PostgreSQL equivalents and runs them idempotently (``IF NOT EXISTS``).

Conversion rules applied:
- ``INTEGER PRIMARY KEY AUTOINCREMENT``  →  ``SERIAL PRIMARY KEY``
- ``(datetime('now'))``                  →  ``NOW()``
- ``REAL``                               →  ``DOUBLE PRECISION``
- Everything else (TEXT, BOOLEAN, INTEGER non-PK, etc.) is kept as-is because
  PostgreSQL understands those type names.

The ``run_migrations`` coroutine accepts any object that exposes an
``execute(sql)`` coroutine — i.e. either a :class:`~storage.postgres.PostgresDB`
instance or (for testing) any compatible mock.
"""

# ---------------------------------------------------------------------------
# Individual DDL statements
# ---------------------------------------------------------------------------

_STATEMENTS: list[str] = [
    # -----------------------------------------------------------------------
    # Core tables
    # -----------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS opportunities (
        id TEXT PRIMARY KEY,
        agent_name TEXT NOT NULL,
        symbol TEXT NOT NULL,
        signal TEXT NOT NULL,
        confidence DOUBLE PRECISION NOT NULL,
        reasoning TEXT NOT NULL,
        suggested_trade TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        expires_at TEXT,
        data TEXT,
        created_at TEXT NOT NULL DEFAULT NOW(),
        updated_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trades (
        id SERIAL PRIMARY KEY,
        opportunity_id TEXT REFERENCES opportunities(id),
        order_result TEXT NOT NULL,
        risk_evaluation TEXT,
        agent_name TEXT,
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS risk_events (
        id SERIAL PRIMARY KEY,
        event_type TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS performance_snapshots (
        id SERIAL PRIMARY KEY,
        agent_name TEXT NOT NULL,
        timestamp TEXT NOT NULL DEFAULT NOW(),
        opportunities_generated INTEGER NOT NULL,
        opportunities_executed INTEGER NOT NULL,
        win_rate DOUBLE PRECISION NOT NULL,
        total_pnl TEXT,
        daily_pnl TEXT,
        daily_pnl_pct DOUBLE PRECISION,
        sharpe_ratio DOUBLE PRECISION,
        max_drawdown DOUBLE PRECISION,
        avg_win TEXT,
        avg_loss TEXT,
        profit_factor DOUBLE PRECISION,
        total_trades INTEGER,
        open_positions INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_snapshots (
        opportunity_id TEXT PRIMARY KEY REFERENCES opportunities(id),
        snapshot_data TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS whatsapp_sessions (
        phone TEXT PRIMARY KEY,
        last_inbound_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tracked_positions (
        id SERIAL PRIMARY KEY,
        agent_name TEXT NOT NULL,
        opportunity_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        entry_price TEXT NOT NULL,
        entry_quantity INTEGER NOT NULL,
        entry_fees TEXT NOT NULL DEFAULT '0',
        entry_time TEXT NOT NULL,
        exit_price TEXT,
        exit_fees TEXT,
        exit_time TEXT,
        exit_reason TEXT,
        max_adverse_excursion TEXT NOT NULL DEFAULT '0',
        status TEXT NOT NULL DEFAULT 'open',
        expires_at TEXT,
        broker_id TEXT,
        account_id TEXT,
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trust_events (
        id SERIAL PRIMARY KEY,
        agent_name TEXT NOT NULL,
        old_level TEXT NOT NULL,
        new_level TEXT NOT NULL,
        changed_by TEXT NOT NULL,
        changed_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_overrides (
        agent_name TEXT PRIMARY KEY,
        trust_level TEXT,
        runtime_parameters TEXT,
        updated_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_results (
        id SERIAL PRIMARY KEY,
        agent_name TEXT NOT NULL,
        parameters TEXT NOT NULL,
        sharpe_ratio DOUBLE PRECISION,
        profit_factor DOUBLE PRECISION,
        total_pnl TEXT,
        max_drawdown DOUBLE PRECISION,
        win_rate DOUBLE PRECISION,
        total_trades INTEGER,
        run_date TEXT NOT NULL,
        data_start TEXT NOT NULL,
        data_end TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tournament_rounds (
        id SERIAL PRIMARY KEY,
        agent_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'running',
        champion_params TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        winner_params TEXT,
        winner_sharpe DOUBLE PRECISION,
        champion_sharpe DOUBLE PRECISION
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tournament_variants (
        id SERIAL PRIMARY KEY,
        round_id INTEGER NOT NULL REFERENCES tournament_rounds(id),
        variant_label TEXT NOT NULL,
        parameters TEXT NOT NULL,
        sharpe_ratio DOUBLE PRECISION,
        profit_factor DOUBLE PRECISION,
        total_pnl TEXT,
        total_trades INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS llm_lessons (
        id SERIAL PRIMARY KEY,
        agent_name TEXT NOT NULL,
        opportunity_id TEXT NOT NULL,
        category TEXT NOT NULL,
        lesson TEXT NOT NULL,
        applies_to TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT NOW(),
        archived_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS llm_prompt_versions (
        id SERIAL PRIMARY KEY,
        agent_name TEXT NOT NULL,
        version INTEGER NOT NULL,
        rules TEXT NOT NULL,
        performance_at_creation TEXT,
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS external_positions (
        id SERIAL PRIMARY KEY,
        broker TEXT NOT NULL,
        account_id TEXT NOT NULL,
        account_name TEXT NOT NULL DEFAULT '',
        symbol TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        quantity TEXT NOT NULL,
        cost_basis TEXT,
        current_value TEXT NOT NULL,
        last_price TEXT NOT NULL,
        imported_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS external_balances (
        id SERIAL PRIMARY KEY,
        broker TEXT NOT NULL,
        account_id TEXT NOT NULL,
        account_name TEXT NOT NULL DEFAULT '',
        net_liquidation TEXT NOT NULL,
        cash TEXT NOT NULL DEFAULT '0',
        imported_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS consensus_votes (
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        opportunity_id TEXT NOT NULL,
        voted_at TEXT NOT NULL,
        PRIMARY KEY (symbol, side, agent_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS leaderboard_cache (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        rankings_json TEXT NOT NULL,
        last_processed_snapshot_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'live'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_remembr_map (
        agent_name TEXT PRIMARY KEY,
        remembr_agent_id TEXT NOT NULL,
        remembr_token TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_autopsies (
        position_id INTEGER PRIMARY KEY,
        autopsy_text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_briefs (
        date TEXT PRIMARY KEY,
        brief_text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS convergence_syntheses (
        convergence_id TEXT PRIMARY KEY,
        synthesis_text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_quality (
        id SERIAL PRIMARY KEY,
        opportunity_id TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        broker_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        expected_price TEXT NOT NULL,
        actual_price TEXT NOT NULL,
        quantity TEXT NOT NULL,
        slippage_bps DOUBLE PRECISION NOT NULL,
        filled_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shadow_executions (
        id TEXT PRIMARY KEY,
        opportunity_id TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        action_level TEXT NOT NULL,
        decision_status TEXT NOT NULL,
        expected_entry_price TEXT,
        expected_quantity TEXT,
        expected_notional TEXT,
        entry_price_source TEXT,
        opportunity_snapshot JSONB,
        risk_snapshot JSONB,
        sizing_snapshot JSONB,
        regime_snapshot JSONB,
        health_snapshot JSONB,
        opened_at TEXT NOT NULL,
        resolve_after TEXT NOT NULL,
        resolved_at TEXT,
        resolution_status TEXT NOT NULL DEFAULT 'pending',
        resolution_price TEXT,
        pnl TEXT,
        return_bps DOUBLE PRECISION,
        max_favorable_bps DOUBLE PRECISION,
        max_adverse_bps DOUBLE PRECISION,
        resolution_notes JSONB
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS position_exit_rules (
        position_id INTEGER PRIMARY KEY,
        rules_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    # -----------------------------------------------------------------------
    # Indexes
    # -----------------------------------------------------------------------
    "CREATE INDEX IF NOT EXISTS idx_opp_agent ON opportunities(agent_name)",
    "CREATE INDEX IF NOT EXISTS idx_opp_symbol ON opportunities(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_opp_status ON opportunities(status)",
    "CREATE INDEX IF NOT EXISTS idx_trades_opp ON trades(opportunity_id)",
    "CREATE INDEX IF NOT EXISTS idx_perf_agent ON performance_snapshots(agent_name)",
    "CREATE INDEX IF NOT EXISTS idx_tracked_agent_status ON tracked_positions(agent_name, status)",
    "CREATE INDEX IF NOT EXISTS idx_tracked_symbol ON tracked_positions(symbol, status)",
    "CREATE INDEX IF NOT EXISTS idx_backtest_agent ON backtest_results(agent_name, run_date)",
    "CREATE INDEX IF NOT EXISTS idx_ext_pos_broker ON external_positions(broker)",
    "CREATE INDEX IF NOT EXISTS idx_ext_pos_symbol ON external_positions(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_ext_bal_broker ON external_balances(broker)",
    "CREATE INDEX IF NOT EXISTS idx_consensus_window ON consensus_votes(symbol, side, voted_at)",
    "CREATE INDEX IF NOT EXISTS idx_exec_quality_agent ON execution_quality(agent_name, filled_at)",
    "CREATE INDEX IF NOT EXISTS idx_shadow_executions_agent_opened ON shadow_executions(agent_name, opened_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_shadow_executions_due ON shadow_executions(resolution_status, resolve_after)",
    "CREATE INDEX IF NOT EXISTS idx_shadow_executions_opportunity ON shadow_executions(opportunity_id)",
    "CREATE INDEX IF NOT EXISTS idx_shadow_executions_symbol_opened ON shadow_executions(symbol, opened_at DESC)",
    # -----------------------------------------------------------------------
    # Bittensor tables
    # -----------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS bittensor_raw_forecasts (
        id SERIAL PRIMARY KEY,
        window_id TEXT NOT NULL,
        request_uuid TEXT NOT NULL,
        collected_at TEXT NOT NULL,
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
        hash_verified INTEGER NOT NULL DEFAULT 0,
        incentive_score DOUBLE PRECISION,
        vtrust DOUBLE PRECISION,
        stake_tao DOUBLE PRECISION,
        metagraph_block INTEGER,
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bt_raw_window ON bittensor_raw_forecasts(window_id)",
    "CREATE INDEX IF NOT EXISTS idx_bt_raw_symbol_time ON bittensor_raw_forecasts(symbol, timeframe, collected_at)",
    "CREATE INDEX IF NOT EXISTS idx_bt_raw_miner ON bittensor_raw_forecasts(miner_hotkey, collected_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_bt_raw_unique ON bittensor_raw_forecasts(window_id, miner_hotkey, request_uuid)",
    """
    CREATE TABLE IF NOT EXISTS bittensor_derived_views (
        window_id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        responder_count INTEGER NOT NULL,
        bullish_count INTEGER NOT NULL,
        bearish_count INTEGER NOT NULL,
        flat_count INTEGER NOT NULL,
        weighted_direction DOUBLE PRECISION NOT NULL,
        weighted_expected_return DOUBLE PRECISION NOT NULL,
        agreement_ratio DOUBLE PRECISION NOT NULL,
        equal_weight_direction DOUBLE PRECISION NOT NULL,
        equal_weight_expected_return DOUBLE PRECISION NOT NULL,
        is_low_confidence INTEGER NOT NULL DEFAULT 0,
        derivation_version TEXT NOT NULL,
        evaluation_status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bt_view_symbol_time ON bittensor_derived_views(symbol, timeframe, timestamp)",
    """
    CREATE TABLE IF NOT EXISTS bittensor_realized_windows (
        window_id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        realized_path TEXT NOT NULL,
        realized_return DOUBLE PRECISION NOT NULL,
        bars_used INTEGER NOT NULL,
        source TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bt_realized_symbol ON bittensor_realized_windows(symbol, timeframe, captured_at)",
    """
    CREATE TABLE IF NOT EXISTS bittensor_accuracy_records (
        id SERIAL PRIMARY KEY,
        window_id TEXT NOT NULL,
        miner_hotkey TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        direction_correct INTEGER NOT NULL,
        predicted_return DOUBLE PRECISION NOT NULL,
        actual_return DOUBLE PRECISION NOT NULL,
        magnitude_error DOUBLE PRECISION NOT NULL,
        path_correlation DOUBLE PRECISION,
        outcome_bars INTEGER NOT NULL,
        scoring_version TEXT NOT NULL,
        evaluated_at TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT NOW(),
        UNIQUE(window_id, miner_hotkey)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bt_acc_miner ON bittensor_accuracy_records(miner_hotkey, evaluated_at)",
    "CREATE INDEX IF NOT EXISTS idx_bt_acc_window ON bittensor_accuracy_records(window_id, miner_hotkey)",
    "CREATE INDEX IF NOT EXISTS idx_bt_acc_symbol ON bittensor_accuracy_records(symbol, timeframe, evaluated_at)",
    """
    CREATE TABLE IF NOT EXISTS bittensor_miner_rankings (
        miner_hotkey TEXT PRIMARY KEY,
        windows_evaluated INTEGER NOT NULL,
        direction_accuracy DOUBLE PRECISION NOT NULL,
        mean_magnitude_error DOUBLE PRECISION NOT NULL,
        mean_path_correlation DOUBLE PRECISION,
        internal_score DOUBLE PRECISION NOT NULL,
        latest_incentive_score DOUBLE PRECISION,
        hybrid_score DOUBLE PRECISION NOT NULL,
        alpha_used DOUBLE PRECISION NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bt_rank_hybrid ON bittensor_miner_rankings(hybrid_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_bt_rank_internal ON bittensor_miner_rankings(internal_score DESC)",
    # -----------------------------------------------------------------------
    # Execution cost attribution tables
    # -----------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS execution_cost_events (
        id SERIAL PRIMARY KEY,
        opportunity_id TEXT,
        tracked_position_id INTEGER,
        order_id TEXT NOT NULL,
        agent_name TEXT,
        symbol TEXT NOT NULL,
        broker_id TEXT,
        account_id TEXT,
        side TEXT NOT NULL,
        order_type TEXT,
        decision_time TEXT NOT NULL,
        decision_bid TEXT,
        decision_ask TEXT,
        decision_last TEXT,
        decision_price TEXT,
        fill_time TEXT,
        fill_price TEXT,
        filled_quantity TEXT NOT NULL,
        fees_total TEXT NOT NULL,
        spread_bps DOUBLE PRECISION,
        slippage_bps DOUBLE PRECISION,
        notional TEXT,
        status TEXT NOT NULL,
        fill_source TEXT NOT NULL DEFAULT 'immediate',
        created_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ece_agent ON execution_cost_events(agent_name, decision_time)",
    "CREATE INDEX IF NOT EXISTS idx_ece_symbol ON execution_cost_events(symbol, decision_time)",
    "CREATE INDEX IF NOT EXISTS idx_ece_broker ON execution_cost_events(broker_id, decision_time)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_ece_order ON execution_cost_events(order_id)",
    """
    CREATE TABLE IF NOT EXISTS execution_cost_stats (
        id SERIAL PRIMARY KEY,
        group_type TEXT NOT NULL,
        group_key TEXT NOT NULL,
        window_label TEXT NOT NULL,
        trade_count INTEGER NOT NULL,
        avg_spread_bps DOUBLE PRECISION,
        median_spread_bps DOUBLE PRECISION,
        avg_slippage_bps DOUBLE PRECISION,
        median_slippage_bps DOUBLE PRECISION,
        p95_slippage_bps DOUBLE PRECISION,
        avg_fee_dollars TEXT NOT NULL,
        rejection_rate DOUBLE PRECISION,
        partial_fill_rate DOUBLE PRECISION,
        created_at TEXT NOT NULL DEFAULT NOW(),
        updated_at TEXT NOT NULL DEFAULT NOW(),
        UNIQUE(group_type, group_key, window_label)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ecs_group ON execution_cost_stats(group_type, group_key)",
    # -----------------------------------------------------------------------
    # Trade analytics (denormalized fact table)
    # -----------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS trade_analytics (
        tracked_position_id INTEGER PRIMARY KEY,
        opportunity_id TEXT,
        agent_name TEXT NOT NULL,
        signal TEXT,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        broker_id TEXT,
        account_id TEXT,
        entry_time TEXT NOT NULL,
        exit_time TEXT NOT NULL,
        hold_minutes DOUBLE PRECISION NOT NULL,
        entry_price TEXT NOT NULL,
        exit_price TEXT NOT NULL,
        entry_quantity INTEGER NOT NULL,
        entry_fees TEXT NOT NULL,
        exit_fees TEXT NOT NULL,
        gross_pnl TEXT NOT NULL,
        net_pnl TEXT NOT NULL,
        gross_return_pct DOUBLE PRECISION NOT NULL,
        net_return_pct DOUBLE PRECISION NOT NULL,
        realized_outcome TEXT NOT NULL,
        exit_reason TEXT,
        confidence DOUBLE PRECISION,
        confidence_bucket TEXT,
        strategy_version TEXT,
        regime_label TEXT,
        trend_regime TEXT,
        volatility_regime TEXT,
        liquidity_regime TEXT,
        execution_slippage_bps DOUBLE PRECISION,
        entry_spread_bps DOUBLE PRECISION,
        order_type TEXT,
        created_at TEXT NOT NULL DEFAULT NOW(),
        updated_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ta_agent_exit ON trade_analytics(agent_name, exit_time)",
    "CREATE INDEX IF NOT EXISTS idx_ta_symbol ON trade_analytics(symbol, agent_name)",
    "CREATE INDEX IF NOT EXISTS idx_ta_regime ON trade_analytics(trend_regime, agent_name)",
    # -----------------------------------------------------------------------
    # Confidence calibration (per-strategy bucket summaries)
    # -----------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS strategy_confidence_calibration (
        agent_name TEXT NOT NULL,
        confidence_bucket TEXT NOT NULL,
        window_label TEXT NOT NULL,
        trade_count INTEGER NOT NULL,
        win_rate DOUBLE PRECISION NOT NULL,
        avg_net_pnl TEXT NOT NULL,
        avg_net_return_pct DOUBLE PRECISION NOT NULL,
        expectancy TEXT NOT NULL,
        profit_factor DOUBLE PRECISION,
        max_drawdown TEXT,
        calibrated_score DOUBLE PRECISION,
        sample_quality TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT NOW(),
        updated_at TEXT NOT NULL DEFAULT NOW(),
        UNIQUE (agent_name, confidence_bucket, window_label)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cc_agent_window ON strategy_confidence_calibration(agent_name, window_label)",
    """
    CREATE TABLE IF NOT EXISTS strategy_health (
        agent_name TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        health_score DOUBLE PRECISION,
        rolling_expectancy TEXT,
        rolling_net_pnl TEXT,
        rolling_drawdown TEXT,
        rolling_win_rate DOUBLE PRECISION,
        rolling_trade_count INTEGER NOT NULL DEFAULT 0,
        throttle_multiplier DOUBLE PRECISION,
        trigger_reason TEXT,
        cooldown_until TEXT,
        manual_override TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_strategy_health_status ON strategy_health(status)",
    """
    CREATE TABLE IF NOT EXISTS strategy_health_events (
        id SERIAL PRIMARY KEY,
        agent_name TEXT NOT NULL,
        old_status TEXT,
        new_status TEXT NOT NULL,
        reason TEXT NOT NULL,
        metrics_snapshot TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        actor TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_she_agent_time ON strategy_health_events(agent_name, created_at)",
    # -----------------------------------------------------------------------
    # Signal-time feature store (one row per routed opportunity)
    # -----------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS signal_features (
        opportunity_id TEXT PRIMARY KEY,
        agent_name TEXT NOT NULL,
        symbol TEXT NOT NULL,
        signal TEXT NOT NULL,
        asset_type TEXT NOT NULL DEFAULT 'STOCK',
        broker_id TEXT,
        confidence DOUBLE PRECISION NOT NULL,
        opportunity_timestamp TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        capture_delay_ms DOUBLE PRECISION,
        feature_version TEXT NOT NULL DEFAULT '1.0',
        quote_bid TEXT,
        quote_ask TEXT,
        quote_last TEXT,
        quote_mid TEXT,
        spread_bps DOUBLE PRECISION,
        rsi_14 DOUBLE PRECISION,
        sma_20 DOUBLE PRECISION,
        ema_20 DOUBLE PRECISION,
        macd_line DOUBLE PRECISION,
        macd_signal DOUBLE PRECISION,
        macd_histogram DOUBLE PRECISION,
        bollinger_upper DOUBLE PRECISION,
        bollinger_middle DOUBLE PRECISION,
        bollinger_lower DOUBLE PRECISION,
        bollinger_pct_b DOUBLE PRECISION,
        atr_14 DOUBLE PRECISION,
        realized_vol_20d DOUBLE PRECISION,
        relative_volume_20d DOUBLE PRECISION,
        distance_to_sma20_pct DOUBLE PRECISION,
        distance_to_ema20_pct DOUBLE PRECISION,
        trend_regime TEXT,
        volatility_regime TEXT,
        liquidity_regime TEXT,
        event_regime TEXT,
        market_state TEXT,
        market_proxy_symbol TEXT,
        market_proxy_rsi_14 DOUBLE PRECISION,
        market_proxy_return_1d DOUBLE PRECISION,
        feature_payload TEXT NOT NULL DEFAULT '{}',
        capture_status TEXT NOT NULL DEFAULT 'captured',
        capture_error TEXT,
        created_at TEXT NOT NULL DEFAULT NOW(),
        updated_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sf_agent_time ON signal_features(agent_name, opportunity_timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_sf_symbol_time ON signal_features(symbol, opportunity_timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_sf_signal_agent ON signal_features(signal, agent_name)",
    # -----------------------------------------------------------------------
    # Tournament audit + agent stages (missing from original Postgres schema)
    # -----------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS tournament_audit_log (
        id SERIAL PRIMARY KEY,
        agent_name TEXT NOT NULL,
        from_stage INTEGER NOT NULL,
        to_stage INTEGER NOT NULL,
        reason TEXT NOT NULL,
        ai_analysis TEXT NOT NULL DEFAULT '',
        ai_recommendation TEXT NOT NULL DEFAULT '',
        timestamp TEXT NOT NULL DEFAULT NOW(),
        overridden_by TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_tournament_audit_agent ON tournament_audit_log(agent_name, timestamp)",
    """
    CREATE TABLE IF NOT EXISTS agent_stages (
        agent_name TEXT PRIMARY KEY,
        current_stage INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    # -----------------------------------------------------------------------
    # Arb spread observations (missing from original Postgres schema)
    # -----------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS arb_spread_observations (
        id SERIAL PRIMARY KEY,
        kalshi_ticker TEXT NOT NULL,
        poly_ticker TEXT NOT NULL,
        match_score DOUBLE PRECISION NOT NULL,
        kalshi_cents INTEGER NOT NULL,
        poly_cents INTEGER NOT NULL,
        gap_cents INTEGER NOT NULL,
        kalshi_volume DOUBLE PRECISION NOT NULL DEFAULT 0,
        poly_volume DOUBLE PRECISION NOT NULL DEFAULT 0,
        observed_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_arb_spread_pair ON arb_spread_observations(kalshi_ticker, poly_ticker, observed_at)",
    "CREATE INDEX IF NOT EXISTS idx_arb_spread_gap ON arb_spread_observations(gap_cents, observed_at)",
    # -----------------------------------------------------------------------
    # Arbitrage execution
    # -----------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS arb_trades (
        id TEXT PRIMARY KEY,
        symbol_a TEXT NOT NULL,
        symbol_b TEXT NOT NULL,
        expected_profit_bps INTEGER NOT NULL,
        state TEXT NOT NULL,
        error_message TEXT,
        created_at TEXT NOT NULL DEFAULT NOW(),
        updated_at TEXT NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_arb_trades_state ON arb_trades(state)",
    """
    CREATE TABLE IF NOT EXISTS arb_legs (
        trade_id TEXT NOT NULL REFERENCES arb_trades(id) ON DELETE CASCADE,
        leg_name TEXT NOT NULL,
        broker_id TEXT NOT NULL,
        order_data TEXT NOT NULL,
        fill_price TEXT,
        fill_quantity TEXT NOT NULL,
        status TEXT NOT NULL,
        external_order_id TEXT,
        PRIMARY KEY (trade_id, leg_name)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_arb_legs_trade_id ON arb_legs(trade_id)",
    # -----------------------------------------------------------------------
    # Agent Registry (Gemini design §1) — replaces agents.yaml as source of truth
    # -----------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS agent_registry (
        id SERIAL PRIMARY KEY,
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
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_agent_registry_name ON agent_registry(name)",
    "CREATE INDEX IF NOT EXISTS idx_agent_registry_status ON agent_registry(status)",
    "CREATE INDEX IF NOT EXISTS idx_agent_registry_strategy ON agent_registry(strategy)",
    "CREATE INDEX IF NOT EXISTS idx_agent_registry_created_by ON agent_registry(created_by)",
    "CREATE INDEX IF NOT EXISTS idx_agent_registry_parent ON agent_registry(parent_name)",
]


async def run_migrations(db) -> None:
    """Run all CREATE TABLE / CREATE INDEX statements against *db*.

    Each statement is executed individually so a single failure does not abort
    the entire migration.  This also makes it easy to add new statements later
    without worrying about transaction semantics across the whole batch.

    *db* must expose an ``execute(sql: str)`` coroutine — any
    :class:`~storage.postgres.PostgresDB` instance satisfies this.
    """
    for stmt in _STATEMENTS:
        stmt = stmt.strip()
        if stmt:
            await db.execute(stmt)

    # Column additions for existing databases (idempotent — ignored if column exists)
    for col, col_def in [("broker_id", "TEXT"), ("account_id", "TEXT")]:
        try:
            await db.execute(
                f"ALTER TABLE tracked_positions ADD COLUMN IF NOT EXISTS {col} {col_def}"
            )
        except Exception:
            pass

    # Add evaluation_status to bittensor_derived_views
    try:
        await db.execute(
            "ALTER TABLE bittensor_derived_views ADD COLUMN IF NOT EXISTS evaluation_status TEXT NOT NULL DEFAULT 'pending'"
        )
    except Exception:
        pass

    # Add remembr_token to agent_remembr_map
    try:
        await db.execute(
            "ALTER TABLE agent_remembr_map ADD COLUMN IF NOT EXISTS remembr_token TEXT"
        )
    except Exception:
        pass
