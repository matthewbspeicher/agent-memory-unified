from __future__ import annotations
import logging
import ssl as _ssl
import aiosqlite
from storage.postgres import PostgresDB
from config import Config

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Database connection manager that accepts Config parameter.

    Handles both SQLite and PostgreSQL connections based on config.database_url.
    """

    def __init__(self, config: Config):
        self.config = config
        self.connection = None

    async def connect(self):
        """
        Establish database connection based on configuration.

        Returns:
            Either an aiosqlite.Connection or PostgresDB instance
        """
        if self.config.database_url:
            # PostgreSQL mode
            import asyncpg  # optional dependency

            if self.config.database_ssl:
                ssl_ctx = _ssl.create_default_context()
                if not self.config.database_ssl_verify:
                    ssl_ctx.check_hostname = False
                    ssl_ctx.verify_mode = _ssl.CERT_NONE
            else:
                ssl_ctx = None

            pool = await asyncpg.create_pool(
                self.config.database_url,
                ssl=ssl_ctx,
                statement_cache_size=0,
            )
            self.connection = PostgresDB(pool)
            # DISABLED: Laravel now owns all DDL via migrations
            # await run_migrations(self.connection)
            logger.info("Connected to PostgreSQL (DDL managed by Laravel)")
            return self.connection

        # SQLite mode
        self.connection = await aiosqlite.connect(self.config.db_path or "data.db")
        self.connection.row_factory = aiosqlite.Row
        await self.connection.execute("PRAGMA journal_mode=WAL")
        await self.connection.execute("PRAGMA busy_timeout=5000")
        await init_db(self.connection)
        return self.connection

    async def close(self):
        """Close the database connection"""
        if self.connection is None:
            return

        if hasattr(self.connection, "pool"):
            # PostgresDB
            await self.connection.pool.close()
        else:
            # aiosqlite
            await self.connection.close()

    async def __aenter__(self):
        """Async context manager entry"""
        return await self.connect()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


async def init_db(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id TEXT PRIMARY KEY,
            agent_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            signal TEXT NOT NULL,
            confidence REAL NOT NULL,
            reasoning TEXT NOT NULL,
            suggested_trade TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            expires_at TEXT,
            data TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id TEXT REFERENCES opportunities(id),
            order_result TEXT NOT NULL,
            risk_evaluation TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS risk_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS performance_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            opportunities_generated INTEGER NOT NULL,
            opportunities_executed INTEGER NOT NULL,
            win_rate REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS opportunity_snapshots (
            opportunity_id TEXT PRIMARY KEY REFERENCES opportunities(id),
            snapshot_data TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS whatsapp_sessions (
            phone TEXT PRIMARY KEY,
            last_inbound_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tracked_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS trust_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            old_level TEXT NOT NULL,
            new_level TEXT NOT NULL,
            changed_by TEXT NOT NULL,
            changed_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_overrides (
            agent_name TEXT PRIMARY KEY,
            trust_level TEXT,
            runtime_parameters TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            parameters TEXT NOT NULL,
            sharpe_ratio REAL,
            profit_factor REAL,
            total_pnl TEXT,
            max_drawdown REAL,
            win_rate REAL,
            total_trades INTEGER,
            run_date TEXT NOT NULL,
            data_start TEXT NOT NULL,
            data_end TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tournament_rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            champion_params TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            winner_params TEXT,
            winner_sharpe REAL,
            champion_sharpe REAL
        );

        CREATE TABLE IF NOT EXISTS tournament_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL REFERENCES tournament_rounds(id),
            variant_label TEXT NOT NULL,
            parameters TEXT NOT NULL,
            sharpe_ratio REAL,
            profit_factor REAL,
            total_pnl TEXT,
            total_trades INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS bittensor_processed_positions (
            position_uuid TEXT PRIMARY KEY,
            miner_hotkey TEXT NOT NULL,
            processed_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_context_cache (
            agent_name TEXT PRIMARY KEY,
            l0_text TEXT NOT NULL,
            l1_text TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            trade_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS llm_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            opportunity_id TEXT NOT NULL,
            category TEXT NOT NULL,
            lesson TEXT NOT NULL,
            applies_to TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            archived_at TEXT
        );

        CREATE TABLE IF NOT EXISTS llm_prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            rules TEXT NOT NULL,
            performance_at_creation TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tournament_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            from_stage INTEGER NOT NULL,
            to_stage INTEGER NOT NULL,
            reason TEXT NOT NULL,
            ai_analysis TEXT NOT NULL DEFAULT '',
            ai_recommendation TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            overridden_by TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tournament_audit_agent
            ON tournament_audit_log(agent_name, timestamp);

        CREATE TABLE IF NOT EXISTS agent_stages (
            agent_name TEXT PRIMARY KEY,
            current_stage INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_opp_agent ON opportunities(agent_name);
        CREATE INDEX IF NOT EXISTS idx_opp_symbol ON opportunities(symbol);
        CREATE INDEX IF NOT EXISTS idx_opp_status ON opportunities(status);
        CREATE INDEX IF NOT EXISTS idx_trades_opp ON trades(opportunity_id);
        CREATE INDEX IF NOT EXISTS idx_perf_agent ON performance_snapshots(agent_name);
        CREATE INDEX IF NOT EXISTS idx_tracked_agent_status ON tracked_positions(agent_name, status);
        CREATE INDEX IF NOT EXISTS idx_tracked_symbol ON tracked_positions(symbol, status);
        CREATE INDEX IF NOT EXISTS idx_backtest_agent ON backtest_results(agent_name, run_date);

        CREATE TABLE IF NOT EXISTS external_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );

        CREATE TABLE IF NOT EXISTS external_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker TEXT NOT NULL,
            account_id TEXT NOT NULL,
            account_name TEXT NOT NULL DEFAULT '',
            net_liquidation TEXT NOT NULL,
            cash TEXT NOT NULL DEFAULT '0',
            imported_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ext_pos_broker ON external_positions(broker);
        CREATE INDEX IF NOT EXISTS idx_ext_pos_symbol ON external_positions(symbol);
        CREATE INDEX IF NOT EXISTS idx_ext_bal_broker ON external_balances(broker);

        CREATE TABLE IF NOT EXISTS consensus_votes (
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            opportunity_id TEXT NOT NULL,
            voted_at TEXT NOT NULL,
            PRIMARY KEY (symbol, side, agent_name)
        );
        CREATE INDEX IF NOT EXISTS idx_consensus_window
            ON consensus_votes(symbol, side, voted_at);

        CREATE TABLE IF NOT EXISTS leaderboard_cache (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            rankings_json TEXT NOT NULL,
            last_processed_snapshot_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'live'
        );

        CREATE TABLE IF NOT EXISTS agent_remembr_map (
            agent_name TEXT PRIMARY KEY,
            remembr_agent_id TEXT NOT NULL,
            remembr_token TEXT
        );

        CREATE TABLE IF NOT EXISTS trade_autopsies (
            position_id INTEGER PRIMARY KEY,
            autopsy_text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS daily_briefs (
            date TEXT PRIMARY KEY,
            brief_text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS convergence_syntheses (
            convergence_id TEXT PRIMARY KEY,
            synthesis_text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS execution_quality (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            broker_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            expected_price TEXT NOT NULL,
            actual_price TEXT NOT NULL,
            quantity TEXT NOT NULL,
            slippage_bps REAL NOT NULL,
            filled_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_exec_quality_agent ON execution_quality(agent_name, filled_at);

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
            opportunity_snapshot TEXT,
            risk_snapshot TEXT,
            sizing_snapshot TEXT,
            regime_snapshot TEXT,
            health_snapshot TEXT,
            opened_at TEXT NOT NULL,
            resolve_after TEXT NOT NULL,
            resolved_at TEXT,
            resolution_status TEXT NOT NULL DEFAULT 'pending',
            resolution_price TEXT,
            pnl TEXT,
            return_bps REAL,
            max_favorable_bps REAL,
            max_adverse_bps REAL,
            resolution_notes TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_executions_agent_opened
            ON shadow_executions(agent_name, opened_at DESC);
        CREATE INDEX IF NOT EXISTS idx_shadow_executions_due
            ON shadow_executions(resolution_status, resolve_after);
        CREATE INDEX IF NOT EXISTS idx_shadow_executions_opportunity
            ON shadow_executions(opportunity_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_executions_symbol_opened
            ON shadow_executions(symbol, opened_at DESC);

        -- Agent Registry (Gemini design §1) — replaces agents.yaml as source of truth
        CREATE TABLE IF NOT EXISTS agent_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            strategy TEXT NOT NULL,
            schedule TEXT NOT NULL DEFAULT 'continuous',
            interval_or_cron INTEGER NOT NULL DEFAULT 60,
            universe TEXT NOT NULL DEFAULT '[]',
            parameters TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            trust_level TEXT NOT NULL DEFAULT 'monitored',
            runtime_overrides TEXT NOT NULL DEFAULT '{}',
            promotion_criteria TEXT NOT NULL DEFAULT '{}',
            shadow_mode INTEGER NOT NULL DEFAULT 0,
            created_by TEXT NOT NULL DEFAULT 'human',
            parent_name TEXT,
            generation INTEGER NOT NULL DEFAULT 1,
            creation_context TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_agent_registry_name ON agent_registry(name);
        CREATE INDEX IF NOT EXISTS idx_agent_registry_status ON agent_registry(status);
        CREATE INDEX IF NOT EXISTS idx_agent_registry_strategy ON agent_registry(strategy);
        CREATE INDEX IF NOT EXISTS idx_agent_registry_created_by ON agent_registry(created_by);
        CREATE INDEX IF NOT EXISTS idx_agent_registry_parent ON agent_registry(parent_name);

        CREATE TABLE IF NOT EXISTS position_exit_rules (
            position_id INTEGER PRIMARY KEY,
            rules_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS arb_spread_observations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            kalshi_ticker TEXT NOT NULL,
            poly_ticker   TEXT NOT NULL,
            match_score   REAL NOT NULL,
            kalshi_cents  INTEGER NOT NULL,
            poly_cents    INTEGER NOT NULL,
            gap_cents     INTEGER NOT NULL,
            kalshi_volume REAL NOT NULL DEFAULT 0,
            poly_volume   REAL NOT NULL DEFAULT 0,
            observed_at   TEXT NOT NULL DEFAULT (datetime('now')),
            is_claimed    BOOLEAN DEFAULT 0,
            claimed_at    TEXT,
            claimed_by    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_arb_spread_pair
            ON arb_spread_observations(kalshi_ticker, poly_ticker, observed_at);
        CREATE INDEX IF NOT EXISTS idx_arb_spread_gap
            ON arb_spread_observations(gap_cents, observed_at);

        CREATE TABLE IF NOT EXISTS arb_trades (
            id TEXT PRIMARY KEY,
            symbol_a TEXT NOT NULL,
            symbol_b TEXT NOT NULL,
            expected_profit_bps INTEGER NOT NULL,
            sequencing TEXT NOT NULL,
            state TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_arb_trades_state ON arb_trades(state);

        CREATE TABLE IF NOT EXISTS arb_legs (
            trade_id TEXT NOT NULL,
            leg_name TEXT NOT NULL,
            broker_id TEXT NOT NULL,
            order_data TEXT NOT NULL,
            fill_price TEXT,
            fill_quantity TEXT NOT NULL,
            status TEXT NOT NULL,
            external_order_id TEXT,
            PRIMARY KEY (trade_id, leg_name),
            FOREIGN KEY (trade_id) REFERENCES arb_trades(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_arb_legs_trade_id ON arb_legs(trade_id);

        CREATE TABLE IF NOT EXISTS bittensor_raw_forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            incentive_score REAL,
            vtrust REAL,
            stake_tao REAL,
            metagraph_block INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_bt_raw_window ON bittensor_raw_forecasts(window_id);
        CREATE INDEX IF NOT EXISTS idx_bt_raw_symbol_time ON bittensor_raw_forecasts(symbol, timeframe, collected_at);
        CREATE INDEX IF NOT EXISTS idx_bt_raw_miner ON bittensor_raw_forecasts(miner_hotkey, collected_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_bt_raw_unique
            ON bittensor_raw_forecasts(window_id, miner_hotkey, request_uuid);

        CREATE TABLE IF NOT EXISTS bittensor_derived_views (
            window_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            responder_count INTEGER NOT NULL,
            bullish_count INTEGER NOT NULL,
            bearish_count INTEGER NOT NULL,
            flat_count INTEGER NOT NULL,
            weighted_direction REAL NOT NULL,
            weighted_expected_return REAL NOT NULL,
            agreement_ratio REAL NOT NULL,
            equal_weight_direction REAL NOT NULL,
            equal_weight_expected_return REAL NOT NULL,
            is_low_confidence INTEGER NOT NULL DEFAULT 0,
            derivation_version TEXT NOT NULL,
            evaluation_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_bt_view_symbol_time ON bittensor_derived_views(symbol, timeframe, timestamp);

        CREATE TABLE IF NOT EXISTS bittensor_realized_windows (
            window_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            realized_path TEXT NOT NULL,
            realized_return REAL NOT NULL,
            bars_used INTEGER NOT NULL,
            source TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_bt_realized_symbol ON bittensor_realized_windows(symbol, timeframe, captured_at);

        CREATE TABLE IF NOT EXISTS bittensor_accuracy_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            window_id TEXT NOT NULL,
            miner_hotkey TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            direction_correct INTEGER NOT NULL,
            predicted_return REAL NOT NULL,
            actual_return REAL NOT NULL,
            magnitude_error REAL NOT NULL,
            path_correlation REAL,
            outcome_bars INTEGER NOT NULL,
            scoring_version TEXT NOT NULL,
            evaluated_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(window_id, miner_hotkey)
        );
        CREATE INDEX IF NOT EXISTS idx_bt_acc_miner ON bittensor_accuracy_records(miner_hotkey, evaluated_at);
        CREATE INDEX IF NOT EXISTS idx_bt_acc_window ON bittensor_accuracy_records(window_id, miner_hotkey);
        CREATE INDEX IF NOT EXISTS idx_bt_acc_symbol ON bittensor_accuracy_records(symbol, timeframe, evaluated_at);

        CREATE TABLE IF NOT EXISTS bittensor_miner_rankings (
            miner_hotkey TEXT PRIMARY KEY,
            windows_evaluated INTEGER NOT NULL,
            direction_accuracy REAL NOT NULL,
            mean_magnitude_error REAL NOT NULL,
            mean_path_correlation REAL,
            internal_score REAL NOT NULL,
            latest_incentive_score REAL,
            hybrid_score REAL NOT NULL,
            alpha_used REAL NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_bt_rank_hybrid ON bittensor_miner_rankings(hybrid_score DESC);
        CREATE INDEX IF NOT EXISTS idx_bt_rank_internal ON bittensor_miner_rankings(internal_score DESC);

        CREATE TABLE IF NOT EXISTS execution_cost_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            spread_bps REAL,
            slippage_bps REAL,
            notional TEXT,
            status TEXT NOT NULL,
            fill_source TEXT NOT NULL DEFAULT 'immediate',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ece_agent ON execution_cost_events(agent_name, decision_time);
        CREATE INDEX IF NOT EXISTS idx_ece_symbol ON execution_cost_events(symbol, decision_time);
        CREATE INDEX IF NOT EXISTS idx_ece_broker ON execution_cost_events(broker_id, decision_time);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ece_order ON execution_cost_events(order_id);

        CREATE TABLE IF NOT EXISTS execution_cost_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_type TEXT NOT NULL,
            group_key TEXT NOT NULL,
            window_label TEXT NOT NULL,
            trade_count INTEGER NOT NULL,
            avg_spread_bps REAL,
            median_spread_bps REAL,
            avg_slippage_bps REAL,
            median_slippage_bps REAL,
            p95_slippage_bps REAL,
            avg_fee_dollars TEXT NOT NULL,
            rejection_rate REAL,
            partial_fill_rate REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(group_type, group_key, window_label)
        );
        CREATE INDEX IF NOT EXISTS idx_ecs_group ON execution_cost_stats(group_type, group_key);

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
            hold_minutes REAL NOT NULL,
            entry_price TEXT NOT NULL,
            exit_price TEXT NOT NULL,
            entry_quantity INTEGER NOT NULL,
            entry_fees TEXT NOT NULL,
            exit_fees TEXT NOT NULL,
            gross_pnl TEXT NOT NULL,
            net_pnl TEXT NOT NULL,
            gross_return_pct REAL NOT NULL,
            net_return_pct REAL NOT NULL,
            realized_outcome TEXT NOT NULL,
            exit_reason TEXT,
            confidence REAL,
            confidence_bucket TEXT,
            strategy_version TEXT,
            regime_label TEXT,
            trend_regime TEXT,
            volatility_regime TEXT,
            liquidity_regime TEXT,
            execution_slippage_bps REAL,
            entry_spread_bps REAL,
            order_type TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ta_agent_exit ON trade_analytics(agent_name, exit_time);
        CREATE INDEX IF NOT EXISTS idx_ta_symbol ON trade_analytics(symbol, agent_name);
        CREATE INDEX IF NOT EXISTS idx_ta_regime ON trade_analytics(trend_regime, agent_name);

        CREATE TABLE IF NOT EXISTS strategy_confidence_calibration (
            agent_name TEXT NOT NULL,
            confidence_bucket TEXT NOT NULL,
            window_label TEXT NOT NULL,
            trade_count INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            avg_net_pnl TEXT NOT NULL,
            avg_net_return_pct REAL NOT NULL,
            expectancy TEXT NOT NULL,
            profit_factor REAL,
            max_drawdown TEXT,
            calibrated_score REAL,
            sample_quality TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (agent_name, confidence_bucket, window_label)
        );
        CREATE INDEX IF NOT EXISTS idx_cc_agent_window
            ON strategy_confidence_calibration(agent_name, window_label);

        CREATE TABLE IF NOT EXISTS strategy_health (
            agent_name TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            health_score REAL,
            rolling_expectancy TEXT,
            rolling_net_pnl TEXT,
            rolling_drawdown TEXT,
            rolling_win_rate REAL,
            rolling_trade_count INTEGER NOT NULL DEFAULT 0,
            throttle_multiplier REAL,
            trigger_reason TEXT,
            cooldown_until TEXT,
            manual_override TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_health_status
            ON strategy_health(status);

        CREATE TABLE IF NOT EXISTS strategy_health_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            reason TEXT NOT NULL,
            metrics_snapshot TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            actor TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_she_agent_time
            ON strategy_health_events(agent_name, created_at);

        CREATE TABLE IF NOT EXISTS signal_features (
            opportunity_id TEXT PRIMARY KEY,
            agent_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            signal TEXT NOT NULL,
            asset_type TEXT NOT NULL DEFAULT 'STOCK',
            broker_id TEXT,
            confidence REAL NOT NULL,
            opportunity_timestamp TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            capture_delay_ms REAL,
            feature_version TEXT NOT NULL DEFAULT '1.0',
            quote_bid TEXT,
            quote_ask TEXT,
            quote_last TEXT,
            quote_mid TEXT,
            spread_bps REAL,
            rsi_14 REAL,
            sma_20 REAL,
            ema_20 REAL,
            macd_line REAL,
            macd_signal REAL,
            macd_histogram REAL,
            bollinger_upper REAL,
            bollinger_middle REAL,
            bollinger_lower REAL,
            bollinger_pct_b REAL,
            atr_14 REAL,
            realized_vol_20d REAL,
            relative_volume_20d REAL,
            distance_to_sma20_pct REAL,
            distance_to_ema20_pct REAL,
            trend_regime TEXT,
            volatility_regime TEXT,
            liquidity_regime TEXT,
            event_regime TEXT,
            market_state TEXT,
            market_proxy_symbol TEXT,
            market_proxy_rsi_14 REAL,
            market_proxy_return_1d REAL,
            feature_payload TEXT NOT NULL DEFAULT '{}',
            capture_status TEXT NOT NULL DEFAULT 'captured',
            capture_error TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_sf_agent_time
            ON signal_features(agent_name, opportunity_timestamp);
        CREATE INDEX IF NOT EXISTS idx_sf_symbol_time
            ON signal_features(symbol, opportunity_timestamp);
        CREATE INDEX IF NOT EXISTS idx_sf_signal_agent
            ON signal_features(signal, agent_name);
    """)

    for col, col_def in [
        ("agent_name", "TEXT"),
    ]:
        try:
            await db.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_def}")
        except Exception:
            pass

    # Migrations for tracked_positions
    for col, col_def in [
        ("expires_at", "TEXT"),
        ("broker_id", "TEXT"),
        ("account_id", "TEXT"),
    ]:
        try:
            await db.execute(
                f"ALTER TABLE tracked_positions ADD COLUMN {col} {col_def}"
            )
        except Exception:
            pass

    for col, col_def in [
        ("total_pnl", "TEXT"),
        ("daily_pnl", "TEXT"),
        ("daily_pnl_pct", "REAL"),
        ("sharpe_ratio", "REAL"),
        ("max_drawdown", "REAL"),
        ("avg_win", "TEXT"),
        ("avg_loss", "TEXT"),
        ("profit_factor", "REAL"),
        ("total_trades", "INTEGER"),
        ("open_positions", "INTEGER"),
    ]:
        try:
            await db.execute(
                f"ALTER TABLE performance_snapshots ADD COLUMN {col} {col_def}"
            )
        except Exception:
            pass

    # Migration: add evaluation_status to bittensor_derived_views
    try:
        await db.execute(
            "ALTER TABLE bittensor_derived_views ADD COLUMN evaluation_status TEXT NOT NULL DEFAULT 'pending'"
        )
    except Exception:
        pass  # Column already exists


async def get_db(path: str = "data.db") -> aiosqlite.Connection:
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await init_db(db)
    return db


async def create_db(config: Config):
    """
    Create and return a database connection.

    Returns either an aiosqlite connection or a :class:`~storage.postgres.PostgresDB`
    depending on whether ``config.database_url`` is set.

    Args:
        config: Config instance with database settings

    Returns:
        Database connection (aiosqlite.Connection or PostgresDB)

    Usage::

        from config import load_config
        config = load_config()
        db = await create_db(config)
        app.state.db = db
    """
    db_conn = DatabaseConnection(config)
    return await db_conn.connect()
