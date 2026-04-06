import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from broker.errors import (
    BrokerConnectionError,
    BrokerError,
    InsufficientFunds,
    InvalidSymbol,
    MarketClosed,
    OrderRejected,
    RateLimitExceeded,
)
from api.deps import (
    set_broker,
    set_agent_runner,
    set_opportunity_store,
    set_risk_engine,
    set_event_bus,
)
from api.routes import (
    health,
    accounts,
    market_data,
    orders,
    trades,
    agents,
    opportunities,
    risk,
    ws,
    analytics,
    experiments,
    tuning,
)
from broker.interfaces import Broker
from config import Config, load_config
from storage.pnl import TrackedPositionStore
from storage.performance import PerformanceStore
from storage.agent_registry import AgentStore
from learning.pnl import TradeTracker
from learning.prompt_store import SqlPromptStore
from integrations.bittensor.models import RankingConfig
from api.routes.learning import create_learning_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    broker = getattr(app.state, "broker", None)
    config = getattr(app.state, "config", load_config())
    if broker:
        set_broker(broker)

    enabled = getattr(app.state, "enable_agent_framework", False)

    from utils.background_tasks import BackgroundTaskManager
    task_mgr = BackgroundTaskManager()
    app.state.task_manager = task_mgr

    # Initialize deps module with app.state reference
    from api.deps import _init_state
    _init_state(app.state)

    # Telemetry setup - conditional, deferred from import time
    from utils.telemetry import setup_telemetry

    setup_telemetry()

    runner = None
    if enabled:
        import logging
        import pathlib
        import yaml
        from pydantic import ValidationError
        from utils.config_loader import ConfigLoader

        _log = logging.getLogger(__name__)
        _app_root = pathlib.Path(__file__).resolve().parent.parent

        import os

        config_loader = ConfigLoader(app_root=_app_root)

        # --- Fail-fast config validation (before DB init or broker connect) ---
        try:
            from risk.config import RiskConfigSchema
            from agents.config import AgentsFileSchema, _ensure_strategies_registered
            from learning.config import LearningConfig

            # 1. Resolve and load Risk Config
            _risk_path_str = config_loader.resolve("risk.yaml")
            _risk_data = config_loader.load_yaml("risk.yaml")

            if _risk_data:
                RiskConfigSchema(**_risk_data.get("risk", _risk_data))
            else:
                _log.warning(
                    "Config validation: risk.yaml not found, skipping validation"
                )

            # 2. Resolve and load Agents Config
            if config.agents_config:
                _agents_yaml_name = config.agents_config
            elif config.paper_trading:
                _agents_yaml_name = "agents.paper.yaml"
            else:
                _agents_yaml_name = "agents.yaml"

            _agents_path_str = config_loader.resolve(_agents_yaml_name)
            _agents_data = config_loader.load_yaml(_agents_yaml_name)

            if _agents_data:
                _ensure_strategies_registered()
                AgentsFileSchema(agents=_agents_data.get("agents", []))
            else:
                _log.warning(
                    "Config validation: agents config not found, skipping validation"
                )

            # 3. Resolve and load Learning Config
            _learning_path_str = config_loader.resolve("learning.yaml")
            _learning_data = config_loader.load_yaml("learning.yaml")

            if _learning_data:
                _learning_cfg = LearningConfig(**_learning_data)
            else:
                _log.warning(
                    "Config validation: learning.yaml not found, using empty config"
                )
                _learning_cfg = LearningConfig(
                    memory={"enabled": False}, strategy_health={"enabled": False}
                )
        except ValidationError as exc:
            _log.critical("Config validation failed: %s", exc.errors())
            raise
        except Exception as exc:
            _log.critical("Config file error: %s", exc)
            raise
        # --- End config validation ---

        from data.bus import DataBus
        from data.signal_bus import SignalBus
        from risk.engine import RiskEngine
        from risk.config import load_risk_config
        from agents.router import OpportunityRouter, ConsensusRouter
        from agents.runner import AgentRunner
        from agents.config import load_agents_config
        from storage.opportunities import OpportunityStore
        from storage.shadow import ShadowExecutionStore
        from storage.trades import TradeStore
        from notifications.log_notifier import LogNotifier

        from storage.db import create_db
        from broker.paper import PaperBroker
        from data.events import EventBus
        from experiments.ab_test import get_experiment_manager
        from execution.shadow import ShadowExecutor, ShadowOutcomeResolver

        event_bus = EventBus()
        signal_bus = SignalBus()
        set_event_bus(event_bus)
        app.state.event_bus = event_bus

        # --- Redis Connection (for hybrid authentication and caching) ---
        if config.redis_url:
            try:
                from redis.asyncio import from_url as redis_from_url
                redis = await redis_from_url(config.redis_url, decode_responses=True)
                app.state.redis = redis
                _log.info("Redis connected for authentication")
            except ImportError:
                _log.warning("redis-py not installed — authentication will fail")
            except Exception as redis_exc:
                _log.warning("Redis connection failed: %s", redis_exc)

        # --- Redis Signal Bridge (Track 20) ---
        if config.redis_url:
            try:
                from data.redis_bridge import RedisSignalBridge

                node_id = "oracle" if config.worker_mode else "primary"
                redis_bridge = RedisSignalBridge(
                    event_bus=event_bus, redis_url=config.redis_url, node_id=node_id
                )
                await redis_bridge.start()
                app.state.redis_bridge = redis_bridge
            except ImportError:
                _log.warning(
                    "redis-py not installed — distributed signal bridge disabled"
                )
            except Exception as rb_exc:
                _log.warning("RedisSignalBridge startup failed: %s", rb_exc)

        db = await create_db(config)
        app.state.db = db
        app.state.learning_config = _learning_cfg

        from llm.client import LLMClient
        llm_client = LLMClient(
            anthropic_key=config.anthropic_api_key,
            groq_key=config.groq_api_key,
            ollama_url=config.ollama_base_url,
            bedrock_region=config.bedrock_region,
            bedrock_model=config.bedrock_model,
            bedrock_access_key_id=config.bedrock_access_key_id,
            bedrock_secret_access_key=config.bedrock_secret_access_key,
        )
        app.state.llm_client = llm_client

        # --- Broker Setup ---
        from api.startup.brokers import setup_brokers

        broker, _all_brokers, _paper_store = await setup_brokers(
            config=config,
            db=db,
            broker=broker,
        )
        if broker:
            set_broker(broker)
            app.state.broker = broker


        # Data sources (Yahoo always available, broker source optional)
        opp_store = OpportunityStore(db)
        set_opportunity_store(opp_store)
        app.state.opportunity_store = opp_store
        trade_store = TradeStore(db)
        from api.deps import set_trade_store

        set_trade_store(trade_store)
        app.state.trade_store = trade_store

        from data.sources.yahoo import YahooFinanceSource
        from data.sources.broker_source import BrokerSource

        yahoo = YahooFinanceSource()
        broker_source = (
            None if config.paper_trading or broker is None else BrokerSource(broker)
        )

        # Massive.com market data (optional — only if configured)
        _sources = [yahoo]
        if broker_source is not None:
            _sources.append(broker_source)
        if config.massive_key:
            try:
                from data.massive import MassiveClient
                from data.massive_source import MassiveDataSource

                _massive_client = MassiveClient(api_key=config.massive_key)
                massive_source = MassiveDataSource(_massive_client)
                # Prepend so Massive is preferred over Yahoo for quotes/bars
                _sources = [massive_source, *_sources]
                app.state.massive_source = massive_source
                _log.info("Massive.com market data integration enabled")
            except Exception as _massive_exc:
                _log.warning(
                    "Massive setup failed (continuing without it): %s", _massive_exc
                )

        _data_bus_account_id = "PAPER" if config.paper_trading else ""
        if broker and not _data_bus_account_id:
            try:
                _accounts = await broker.account.get_accounts()
                if _accounts:
                    _data_bus_account_id = _accounts[0].account_id
            except Exception as _acct_exc:
                _log.warning(
                    "Failed to resolve broker account for DataBus: %s", _acct_exc
                )

        data_bus = DataBus(
            sources=_sources,
            broker=broker,
            trade_store=trade_store,
            account_id=_data_bus_account_id,
            llm_client=llm_client,
            anthropic_key=config.anthropic_api_key,
        )
        app.state.data_bus = data_bus

        shadow_store = ShadowExecutionStore(db)
        shadow_executor = ShadowExecutor(store=shadow_store, data_bus=data_bus)
        shadow_outcome_resolver = ShadowOutcomeResolver(
            store=shadow_store,
            data_bus=data_bus,
        )

        async def _shadow_outcome_resolver_loop() -> None:
            while True:
                try:
                    await shadow_outcome_resolver.resolve_due(limit=25)
                except Exception as exc:
                    _log.warning("Shadow outcome resolver loop failed: %s", exc)
                await asyncio.sleep(60)

        app.state.shadow_execution_store = shadow_store
        app.state.shadow_executor = shadow_executor
        app.state.shadow_outcome_resolver = shadow_outcome_resolver
        task_mgr.create_task(_shadow_outcome_resolver_loop(), name="shadow_outcome_resolver")

        from storage.signal_features import SignalFeatureStore as _SFStore
        from learning.signal_features import SignalFeatureCapture as _SFCapture

        _sf_store = _SFStore(db)
        _sf_capture = _SFCapture(store=_sf_store, data_bus=data_bus)
        app.state.signal_feature_store = _sf_store

        from storage.confidence_calibration import (
            ConfidenceCalibrationStore as _CCStore,
        )
        from learning.confidence_calibration import (
            ConfidenceCalibrationConfig as _RuntimeCCConfig,
        )

        _cc_store = _CCStore(db)
        _cc_cfg = _RuntimeCCConfig(
            enabled=_learning_cfg.confidence_calibration.enabled,
            bucket_width=_learning_cfg.confidence_calibration.bucket_width,
            min_trades_for_usable_bucket=_learning_cfg.confidence_calibration.min_trades_for_usable_bucket,
            min_trades_for_hard_reject=_learning_cfg.confidence_calibration.min_trades_for_hard_reject,
            insufficient_sample_multiplier=_learning_cfg.confidence_calibration.insufficient_sample_multiplier,
            max_positive_multiplier=_learning_cfg.confidence_calibration.max_positive_multiplier,
            max_composed_kelly_fraction=_learning_cfg.confidence_calibration.max_composed_kelly_fraction,
            weak_expectancy_threshold=_learning_cfg.confidence_calibration.weak_expectancy_threshold,
            moderate_expectancy_threshold=_learning_cfg.confidence_calibration.moderate_expectancy_threshold,
            strong_expectancy_threshold=_learning_cfg.confidence_calibration.strong_expectancy_threshold,
            allow_reject=_learning_cfg.confidence_calibration.allow_reject,
        )
        app.state.confidence_calibration_store = _cc_store

        # Wire DataBus into SimulatedBroker now that it's available
        if config.paper_trading and hasattr(broker, "_market_data_provider"):
            broker._market_data_provider._data_bus = data_bus  # type: ignore[attr-defined]

        # Learning system
        pnl_store = TrackedPositionStore(db)
        perf_store = PerformanceStore(db)
        agent_store = AgentStore(db)
        app.state.agent_store = agent_store

        # Bootstrap agent registry from YAML if empty
        try:
            # Reuse already-loaded agents data from validation (cached in config_loader)
            _agent_list = (
                _agents_data.get("agents", []) if isinstance(_agents_data, dict) else []
            )
            count = await agent_store.seed_from_yaml(_agent_list)
            if count > 0:
                _log.info(
                    "Agent registry bootstrapped: %d agents seeded from YAML", count
                )
        except Exception as _seed_reg_exc:
            _log.warning(
                "Agent registry bootstrap failed: %s (non-fatal)", _seed_reg_exc
            )

        from storage.trade_analytics import TradeAnalyticsStore
        from storage.opportunities import OpportunityStore as _OppStoreForAnalytics
        from storage.execution_quality import (
            ExecutionQualityStore as _EQStoreForAnalytics,
        )

        _analytics_store = TradeAnalyticsStore(db)
        _opp_store_for_analytics = _OppStoreForAnalytics(db)
        _exec_quality_store_for_analytics = _EQStoreForAnalytics(db)
        trade_tracker = TradeTracker(
            store=pnl_store,
            data_bus=data_bus,
            analytics_store=_analytics_store,
            opportunity_store=_opp_store_for_analytics,
            execution_quality_store=_exec_quality_store_for_analytics,
            signal_feature_store=_sf_store,
            confidence_calibration_store=_cc_store,
            confidence_calibration_config=_cc_cfg,
        )

        # Local SQLite prompt store — authoritative for all prompt state.
        # Optional remembr mirror can be added later but must fail open to local-only.
        prompt_store = SqlPromptStore(db)

        # Learning API routes
        learning_router = create_learning_router(
            pnl_store=pnl_store,
            perf_store=perf_store,
            agent_store=agent_store,
        )
        app.include_router(learning_router)

        from storage.external import ExternalPortfolioStore as ExtStore

        ext_store = ExtStore(db)
        from api.routes.import_portfolio import create_import_router

        import_router = create_import_router(ext_store)
        app.include_router(import_router)

        from api.routes.backtest import router as backtest_router

        app.include_router(backtest_router)
        from api.routes.sizing import router as sizing_router

        app.include_router(sizing_router)
        from api.routes.execution import router as execution_router

        app.include_router(execution_router)
        from api.routes.regime import router as regime_router

        app.include_router(regime_router)
        from api.routes.arbitrage import router as arb_router

        app.include_router(arb_router)

        # --- Kalshi Integration ---
        from api.startup.integrations import setup_kalshi
        
        _kalshi_source, _kalshi_client = await setup_kalshi(
            config=config,
            data_bus=data_bus,
        )


        # Wire RSS news source if Kalshi is available
        if getattr(data_bus, "_kalshi_source", None):
            try:
                from data.sources.rss_news import RSSNewsSource

                news_source = RSSNewsSource(
                    feed_urls=config.news_feeds or None,
                    llm_client=llm_client,
                    poll_interval=config.news_poll_interval,
                )
                data_bus._news_source = news_source
                task_mgr.create_task(
                    news_source.run(
                        kalshi_source=data_bus._kalshi_source,
                        event_bus=event_bus,
                    ),
                    name="rss_news_source"
                )
                _log.info(
                    "RSSNewsSource started (%d feeds, %ds interval)",
                    len(news_source._feed_urls),
                    config.news_poll_interval,
                )
            except Exception as exc:
                _log.warning("RSSNewsSource startup failed (non-fatal): %s", exc)

        # --- Polymarket Integration ---
        from api.startup.integrations import setup_polymarket
        
        _polymarket_source, polymarket_broker = await setup_polymarket(
            config=config,
            data_bus=data_bus,
            all_brokers=_all_brokers,
        )

        # Multi-broker map — start from connected trading brokers, add prediction markets
        _brokers: dict = dict(_all_brokers)
        if polymarket_broker:
            _brokers["polymarket"] = polymarket_broker
            # Paper broker alongside live (only if paper trading mode is on)
            if config.paper_trading:
                try:
                    from adapters.polymarket.paper import PolymarketPaperBroker

                    _poly_paper = PolymarketPaperBroker(store=_paper_store)
                    await _poly_paper.connection.connect()
                    _brokers["polymarket_paper"] = _poly_paper
                    _log.info("Polymarket paper broker enabled")
                except Exception as _poly_paper_exc:
                    _log.warning(
                        "Polymarket paper broker setup failed: %s", _poly_paper_exc
                    )
        app.state.brokers = _brokers
        app.state.primary_broker = broker

        # --- Journal Setup ---
        from api.startup.observability import setup_journal
        
        journal_manager, journal_indexer = await setup_journal(
            config=config,
            event_bus=event_bus,
            task_manager=task_mgr,
        )
        if journal_manager:
            app.state.journal_manager = journal_manager
        if journal_indexer:
            app.state.journal_indexer = journal_indexer


        # Streaming quotes (optional — opt-in per broker)
        _streams: dict = {}
        if config.alpaca_streaming and "alpaca" in _brokers:
            try:
                from adapters.alpaca.stream import AlpacaStream
                from streaming.base import BrokerStream

                _alpaca_stream = AlpacaStream(
                    api_key=config.alpaca_api_key,
                    secret_key=config.alpaca_secret_key,
                    data_feed=config.alpaca_data_feed,
                )
                _streams["alpaca"] = _alpaca_stream
            except Exception as e:
                _log.warning("AlpacaStream setup failed: %s", e)

        if config.tradier_streaming and "tradier" in _brokers:
            try:
                from adapters.tradier.stream import TradierStream

                _tradier_stream = TradierStream(
                    token=config.tradier_token,
                    sandbox=config.tradier_sandbox,
                )
                _streams["tradier"] = _tradier_stream
            except Exception as e:
                _log.warning("TradierStream setup failed: %s", e)

        # SpreadStore always available on app.state (None when arb not configured)
        app.state.spread_store = None

        # Cross-platform arb (only if both Kalshi and Polymarket configured)
        _kalshi_source = getattr(data_bus, "_kalshi_source", None)
        if _kalshi_source and _polymarket_source:
            from strategies.cross_platform_arb import CrossPlatformArbAgent
            from agents.config import register_strategy as _reg
            from storage.spreads import SpreadStore
            from storage.arbitrage import ArbStore
            from execution.arbitrage import ArbCoordinator
            from strategies.spread_tracker import SpreadTracker

            _spread_store = SpreadStore(db)
            _arb_store = ArbStore(db)
            app.state.spread_store = _spread_store
            app.state.arb_store = _arb_store

            _arb_coordinator = ArbCoordinator(
                brokers=_brokers,
                store=_arb_store,
                config=config,
                meta_agent=None,  # Will be wired after MetaAgent is built
                event_bus=event_bus,
                journal_manager=journal_manager,
            )
            app.state.arb_coordinator = _arb_coordinator

            # match_index is poly_ticker (condition_id) -> kalshi_ticker
            # populated once at startup; refreshed by WS feed background refresh
            _match_index: dict[str, str] = {}
            app.state.arb_match_index = _match_index

            _reg(
                "cross_platform_arb",
                lambda config: CrossPlatformArbAgent(
                    config=config,
                    kalshi_ds=_kalshi_source,
                    polymarket_ds=_polymarket_source,
                    spread_store=_spread_store,
                ),
            )

            # SpreadTracker — listens to polymarket.quote events
            _spread_tracker = SpreadTracker(
                spread_store=_spread_store,
                match_index=_match_index,
                event_bus=event_bus,
                kalshi_ds=_kalshi_source,
                alert_threshold_cents=config.__dict__.get(
                    "arb_alert_threshold_cents", 8
                ),
                notifier=None,  # notifier wired after CompositeNotifier is built below
            )
            task_mgr.create_task(_spread_tracker.run(), name="spread_tracker")

            # Polymarket WebSocket feed (optional — requires polymarket_ws_enabled)
            if getattr(config, "polymarket_ws_enabled", True):
                try:
                    from adapters.polymarket.ws_feed import PolymarketWebSocketFeed

                    _ws_feed = PolymarketWebSocketFeed(
                        data_source=_polymarket_source,
                        event_bus=event_bus,
                    )
                    # Fetch initial token IDs for subscription
                    try:
                        _init_markets = await _polymarket_source.get_markets(limit=200)
                        _token_ids = [m.ticker for m in _init_markets]
                    except Exception as _tok_exc:
                        _log.warning(
                            "Initial Polymarket market fetch failed, starting WS with no tokens: %s",
                            _tok_exc,
                        )
                        _token_ids = []
                    task_mgr.create_task(_ws_feed.run(_token_ids), name="polymarket_ws_feed")
                    _log.info(
                        "PolymarketWebSocketFeed started (%d tokens)", len(_token_ids)
                    )
                except Exception as _ws_exc:
                    _log.warning(
                        "PolymarketWebSocketFeed startup failed (non-fatal): %s",
                        _ws_exc,
                    )

        # Reuse already-loaded risk data from validation (cached in config_loader)
        _log.info("Resolved risk.yaml path string: %s", _risk_path_str)
        if not _risk_data:
            _log.error("CRITICAL: risk.yaml not found at any location!")
            _risk_data = {"rules": [], "kill_switch": {"enabled": False}}

        # NOTE: load_risk_config() still re-reads risk.yaml from disk (line 63 in risk/config.py).
        # To fully eliminate duplicate reads, we would need to refactor load_risk_config() to accept
        # parsed data instead of a path, which is outside the scope of this task.
        if _risk_path_str is None:
            _log.error("CRITICAL: risk.yaml path is None, cannot initialize RiskEngine")
            # Create minimal RiskEngine with no rules
            from risk.engine import RiskEngine
            from risk.kill_switch import KillSwitch
            risk_engine = RiskEngine(rules=[], kill_switch=KillSwitch())
        else:
            risk_engine = load_risk_config(
                _risk_path_str,
                leaderboard=None,
                tournament=None,
                perf_store=perf_store,
                agent_store=agent_store,
                settings=config,
                journal_manager=journal_manager,
            )

        # Start background task to keep Governor cache fresh
        if risk_engine._governor:

            async def _governor_refresh():
                while True:
                    try:
                        await risk_engine._governor._refresh_cache_if_needed()
                    except Exception as e:
                        _log.error("Governor cache refresh failed: %s", e)
                    await asyncio.sleep(60)  # check every minute

            task_mgr.create_task(_governor_refresh(), name="governor_refresh")

        set_risk_engine(risk_engine)
        app.state.risk_engine = risk_engine
        from notifications.composite import CompositeNotifier
        from notifications.slack import SlackNotifier

        active_notifiers = [LogNotifier()]
        api_base = f"http://{config.api_host}:{config.api_port}"

        if config.slack_webhook_url:
            active_notifiers.append(
                SlackNotifier(
                    config.slack_webhook_url, api_base, api_key=config.api_key
                )
            )

        # --- WhatsApp Setup ---
        from api.startup.observability import setup_whatsapp
        
        wa_client, wa_numbers = await setup_whatsapp(
            config=config,
            db=db,
        )
        if wa_client:
            from notifications.whatsapp import WhatsAppNotifier
            from agents.models import ActionLevel
            
            active_notifiers.append(
                WhatsAppNotifier(
                    client=wa_client,
                    allowed_numbers=wa_numbers,
                    action_level=ActionLevel.SUGGEST_TRADE,
                )
            )

        notifier = CompositeNotifier(active_notifiers)

        # --- Observability Setup ---
        from api.startup.observability import setup_observability
        
        _emitter = await setup_observability(
            config=config,
            event_bus=event_bus,
            notifier=notifier,
            task_manager=task_mgr,
        )
        if _emitter:
            app.state.observability_emitter = _emitter

        # Profitable trading engine services
        from sizing.engine import SizingEngine

        sizing_engine = SizingEngine(perf_store=perf_store)
        app.state.sizing_engine = sizing_engine

        exit_manager = None
        exec_tracker = None
        exec_quality_store = None
        exec_cost_store = None
        slippage_loop = None

        if not config.worker_mode:
            from exits.manager import ExitManager
            from storage.exit_rules import ExitRuleStore
            from execution.tracker import ExecutionTracker
            from execution.feedback import SlippageFeedbackLoop
            from storage.execution_quality import ExecutionQualityStore
            from storage.execution_costs import ExecutionCostStore

            exit_rule_store = ExitRuleStore(db)
            exit_manager = ExitManager(store=exit_rule_store)
            await exit_manager.load_rules()
            app.state.exit_manager = exit_manager

            exec_quality_store = ExecutionQualityStore(db)
            exec_tracker = ExecutionTracker(store=exec_quality_store)
            exec_cost_store = ExecutionCostStore(db)
            slippage_loop = SlippageFeedbackLoop(
                tracker=exec_tracker,
                perf_store=perf_store,
                agent_store=agent_store,
            )
            app.state.execution_tracker = exec_tracker
            app.state.execution_store = exec_quality_store
            app.state.execution_cost_store = exec_cost_store
            app.state.slippage_loop = slippage_loop

        from regime.agent_filter import RegimeFilter
        from regime.models import MarketRegime as _MR

        # Build per-agent allowed regimes map for the legacy equity RegimeFilter
        # from the new config fields (regime_policy_mode=static_gate + allowed_regimes).
        # Agents in annotate_only / off / empirical_gate modes skip this map and
        # use DEFAULT_ALLOWED_REGIMES (the legacy behavior).
        _agent_regimes_map: dict[str, set[_MR]] = {}
        # (populated after agent_configs are loaded below; deferred binding via app.state)
        regime_filter = RegimeFilter(agent_regimes=None)
        app.state.regime_filter = regime_filter

        # Remembr.dev Sync (Leaderboard + Agent Registration)
        from leaderboard.remembr_sync import RemembrArenaSync

        remembr_sync = None
        # Use owner token if available for agent registration, fall back to agent token
        registration_token = config.remembr_owner_token or config.remembr_agent_token
        if registration_token:
            remembr_sync = RemembrArenaSync(
                token=registration_token,
                db=db,
                base_url=config.remembr_base_url,
                timeout=config.remembr_timeout,
            )

        # Agent Memory System (optional — only if remembr keys are configured)
        _trade_reflector_factory = None
        if (
            (config.remembr_api_key or config.remembr_owner_token)
            and config.remembr_shared_api_key
            and _learning_data.get("memory", {}).get("enabled", False)
        ):
            try:
                from remembr.client import AsyncRemembrClient
                from learning.memory_client import TradingMemoryClient
                from learning.trade_reflector import TradeReflector

                _mem_cfg = _learning_cfg.memory
                _shared_remembr = AsyncRemembrClient(
                    agent_token=config.remembr_shared_api_key,
                    base_url=config.remembr_base_url,
                )

                async def _make_reflector(agent_name: str) -> TradeReflector:
                    agent_token = config.remembr_api_key
                    
                    # Try to get or register agent-specific token
                    if remembr_sync and agent_name != "_global":
                        try:
                            # ensure_agents_registered ensures they exist and stores tokens in DB
                            await remembr_sync.ensure_agents_registered([agent_name])
                            tokens = await remembr_sync.get_agent_tokens()
                            if agent_name in tokens:
                                agent_token = tokens[agent_name]
                                _log.debug(f"Using autonomous token for agent {agent_name}")
                        except Exception as e:
                            _log.warning(f"Failed to get autonomous token for {agent_name}, falling back: {e}")

                    _private = AsyncRemembrClient(
                        agent_token=agent_token,
                        base_url=config.remembr_base_url,
                    )
                    _mc = TradingMemoryClient(
                        private_client=_private,
                        shared_client=_shared_remembr,
                        ttl_days=_mem_cfg.ttl_days,
                    )
                    return TradeReflector(
                        memory_client=_mc,
                        deep_reflection_pnl_multiplier=_mem_cfg.deep_reflection.pnl_multiplier,
                        deep_reflection_loss_multiplier=_mem_cfg.deep_reflection.loss_multiplier,
                        llm=llm_client,
                    )

                _trade_reflector_factory = _make_reflector

                # Register shared memory client for API endpoints
                from api.routes.memory import register_shared_client

                _shared_mc = TradingMemoryClient(
                    private_client=_shared_remembr,
                    shared_client=_shared_remembr,
                    ttl_days=_mem_cfg.ttl_days,
                )
                register_shared_client(_shared_mc)
                _log.info("Agent memory system enabled (remembr.dev)")
            except Exception as _mem_exc:
                _log.warning(
                    "Memory system setup failed (continuing without it): %s", _mem_exc
                )

        _global_reflector = None
        if _trade_reflector_factory:
            # Note: _global_reflector init is now async, but we can't await here easily if it's used synchronously
            # However, OpportunityRouter takes it. We'll pre-initialize it.
            _global_reflector = await _trade_reflector_factory("_global")

        # Strategy Health Engine (always wired — optional execution enforcement)
        from learning.strategy_health import StrategyHealthEngine
        from learning.strategy_health import StrategyHealthConfig as _SHConfig
        from storage.strategy_health import StrategyHealthStore as _SHStore

        _sh_store = _SHStore(db)
        _sh_cfg = _SHConfig.from_learning_config(
            getattr(_learning_cfg, "strategy_health", None)
        )
        health_engine = StrategyHealthEngine(
            health_store=_sh_store,
            perf_store=perf_store,
            config=_sh_cfg,
        )
        app.state.health_engine = health_engine

        router = OpportunityRouter(
            store=opp_store,
            notifier=notifier,
            risk_engine=risk_engine,
            broker=broker,
            brokers=_brokers,
            broker_routing=config.broker_routing,
            trade_store=trade_store,
            data_bus=data_bus,
            event_bus=event_bus,
            experiment_manager=get_experiment_manager(),
            trade_tracker=trade_tracker,
            sizing_engine=sizing_engine,
            exit_manager=exit_manager,
            execution_tracker=exec_tracker,
            regime_filter=regime_filter,
            slippage_loop=slippage_loop,
            trade_reflector=_global_reflector,
            health_engine=health_engine,
            signal_feature_capture=_sf_capture,
            execution_cost_store=exec_cost_store,
            confidence_calibration_store=_cc_store,
            confidence_calibration_config=_cc_cfg,
            shadow_executor=shadow_executor,
            journal_manager=journal_manager,
        )

        if config.consensus_threshold > 1:
            from storage.consensus import ConsensusStore

            consensus_store = ConsensusStore(db)
            router = ConsensusRouter(
                target_router=router,
                threshold=config.consensus_threshold,
                window_minutes=config.consensus_window_minutes,
                consensus_store=consensus_store,
            )
        runner = AgentRunner(
            data_bus,
            router,
            event_bus,
            emitter=_emitter,
            signal_bus=signal_bus,
            health_engine=health_engine,
            trade_reflector_factory=_trade_reflector_factory,
            agent_store=agent_store,
        )
        set_agent_runner(runner)
        app.state.agent_runner = runner
        # Back-wire runner into router so _check_regime_policy() can look up per-agent config.
        _base_router = router._target if hasattr(router, "_target") else router
        if hasattr(_base_router, "_runner"):
            _base_router._runner = runner

        # Leaderboard (optional — only if runner + perf_store exist)
        from leaderboard.engine import LeaderboardEngine

        # remembr_sync already initialized above
        leaderboard_engine = LeaderboardEngine(
            perf_store=perf_store,
            runner=runner,
            db=db,
            remembr_sync=remembr_sync,
        )

        # Autonomous Team Setup (requires owner token)
        if remembr_sync and config.remembr_owner_token:
            async def _setup_remembr_team():
                try:
                    agent_names = [a.name for a in runner.list_agents()]
                    await remembr_sync.ensure_team_setup("stock-trading-api", agent_names)
                except Exception as e:
                    _log.warning(f"Autonomous team setup failed: {e}")

            task_mgr.create_task(_setup_remembr_team(), name="remembr_team_setup")
        app.state.leaderboard_engine = leaderboard_engine

        # Seed zero-state performance snapshots so leaderboard isn't empty on cold start
        try:
            agent_names = [a.name for a in runner.list_agents()]
            seeded = await perf_store.seed_if_empty(agent_names)
            if seeded:
                _log.info(
                    "Seeded %d agents with zero-state performance snapshots", seeded
                )
        except Exception as _seed_exc:
            _log.warning("Failed to seed performance snapshots: %s", _seed_exc)

        # Trade Journal (optional — requires pnl_store + opp_store)
        from journal.autopsy import AutopsyGenerator
        from journal.service import JournalService

        autopsy_gen = AutopsyGenerator(
            db=db,
            opp_store=opp_store,
            llm=llm_client,
            journal_manager=journal_manager,
        )
        journal_service = JournalService(
            pnl_store=pnl_store,
            opp_store=opp_store,
            autopsy=autopsy_gen,
        )
        app.state.journal_service = journal_service

        # Morning Brief
        from brief.generator import BriefGenerator

        brief_generator = BriefGenerator(
            db=db,
            llm=llm_client,
        )
        app.state.brief_generator = brief_generator

        # Agent War Room
        from warroom.engine import WarRoomEngine

        warroom_engine = WarRoomEngine(
            db=db,
            llm=llm_client,
        )
        app.state.warroom_engine = warroom_engine

        # Tournament Engine (optional — only if learning config has tournament.enabled)
        from datetime import datetime, timezone

        tournament_engine = None
        if _learning_cfg.tournament.enabled:
            from tournament.engine import TournamentEngine
            from tournament.store import TournamentStore

            _tournament_store = TournamentStore(db)
            tournament_engine = TournamentEngine(
                store=_tournament_store,
                perf_store=perf_store,
                notifier=notifier,
                runner=runner,
                config=_learning_cfg.tournament,
                llm=llm_client,
            )
            app.state.tournament_engine = tournament_engine

            from api.routes.tournament import create_tournament_router

            app.include_router(create_tournament_router(tournament_engine))

        if wa_client:
            # remembr.dev memory for WhatsApp assistant (optional)
            wa_remembr = None
            if config.remembr_api_key:
                try:
                    from remembr.client import AsyncRemembrClient

                    wa_remembr = AsyncRemembrClient(
                        agent_token=config.remembr_api_key,
                        base_url=config.remembr_base_url,
                    )
                    _log.info("WhatsApp assistant memory enabled via remembr.dev")
                except Exception as exc:
                    _log.warning("Failed to init remembr.dev for WhatsApp: %s", exc)

            wa_assistant = WhatsAppAssistant(
                client=wa_client,
                broker=broker,  # SimulatedBroker in paper mode, real broker in live mode
                runner=runner,
                opp_store=opp_store,
                risk_engine=risk_engine,
                llm_client=llm_client,
                external_store=ext_store,
                data_bus=data_bus,
                leaderboard_engine=leaderboard_engine,
                journal_service=journal_service,
                brief_generator=brief_generator,
                warroom_engine=warroom_engine,
                paper_broker=broker if config.paper_trading else None,
                tournament_engine=getattr(app.state, "tournament_engine", None),
                db=db,
                remembr_client=wa_remembr,
                agent_store=agent_store,
            )

            wa_webhook = create_webhook_router(
                assistant=wa_assistant,
                verify_token=config.whatsapp_verify_token or "",
                app_secret=config.whatsapp_app_secret or "",
                allowed_numbers=config.whatsapp_allowed_numbers or "",
            )
            app.include_router(wa_webhook)

            # Start proactive ops background tasks
            wa_assistant.start_proactive(wa_numbers)

            from api.routes.test import create_test_router

            test_router = create_test_router(
                wa_client=wa_client, allowed_numbers=config.whatsapp_allowed_numbers
            )
            app.include_router(test_router)

        if not wa_client:
            from api.routes.test import create_test_router

            app.include_router(create_test_router(wa_client=None, allowed_numbers=None))

        # Reuse already-resolved agents path from validation
        _agents_path = _agents_path_str

        # Re-register exit_monitor with injected dependencies (overrides bare-class default)
        from agents.config import register_strategy
        from strategies.exit_monitor import ExitMonitorAgent as _ExitMonitorAgent

        register_strategy(
            "exit_monitor",
            lambda config: _ExitMonitorAgent(
                config=config,
                exit_manager=exit_manager,
                position_store=pnl_store,
            ),
        )

        # NOTE: load_agents_config() still re-reads agents.yaml from disk (line 182 in agents/config.py).
        # To fully eliminate duplicate reads, we would need to refactor load_agents_config() to accept
        # parsed data instead of a path, which is outside the scope of this task.
        if _agents_path is None:
            _log.error("CRITICAL: agents.yaml path is None, cannot load agent configurations")
            agent_configs = []
        else:
            agent_configs = load_agents_config(str(_agents_path), prompt_store=prompt_store)

        for a in agent_configs:
            runner.register(a)
            if a.config.schedule in ("continuous", "cron"):
                await runner.start_agent(a.name)

        # Start registry polling for dynamic agent lifecycle management
        await runner.start_polling(interval=60)

        # --- MetaAgent + Signal Adapters (Track 13) ---
        try:
            from agents.meta import MetaAgent
            from agents.signal_adapter import SignalAdapterRunner
            from agents.adapters.prediction_market import PredictionMarketAdapter
            from agents.models import AgentConfig as _AC, ActionLevel as _AL

            meta_cfg = _AC(
                name="meta_agent",
                strategy="meta",
                schedule="continuous",
                interval=30,
                action_level=_AL.NOTIFY,
                parameters={
                    "boost_delta": 0.05,
                    "max_cumulative_boost": 0.15,
                    "boost_ttl_minutes": 15,
                },
            )
            meta_agent = MetaAgent(
                config=meta_cfg, runner=runner, signal_bus=signal_bus
            )
            runner.register(meta_agent)
            app.state.meta_agent = meta_agent

            # Inject into router for opportunity annotation
            router._meta_agent = meta_agent

            # Start signal adapters
            adapters = []
            if data_bus:
                adapters.append(PredictionMarketAdapter(data_bus=data_bus))
            if adapters:
                adapter_runner = SignalAdapterRunner(
                    adapters=adapters, signal_bus=signal_bus
                )
                adapter_runner.start(intervals={"prediction_market": 300})
                app.state.adapter_runner = adapter_runner
                _log.info(
                    "Signal adapter runner started with %d adapter(s)", len(adapters)
                )

            await runner.start_agent("meta_agent")
            _log.info("MetaAgent registered and started")

            # Wire to ArbCoordinator if configured
            if "_arb_coordinator" in locals() and _arb_coordinator:
                _arb_coordinator._meta_agent = meta_agent
        except Exception as meta_exc:
            _log.warning("MetaAgent setup failed (non-fatal): %s", meta_exc)

        if _streams:
            from streaming.manager import StreamManager

            _stream_manager = StreamManager(
                streams=_streams,
                data_bus=data_bus,
                event_bus=event_bus,
            )
            await _stream_manager.start()

            # Subscribe to all agent universe symbols
            all_symbols: set[str] = set()
            for agent in agent_configs:
                universe = getattr(agent.config, "universe", [])
                if isinstance(universe, list):
                    all_symbols.update(universe)
            if all_symbols:
                await _stream_manager.subscribe(list(all_symbols))

            app.state.stream_manager = _stream_manager
            _log.info(
                "StreamManager started with %d streams, %d symbols",
                len(_streams),
                len(all_symbols),
            )

        # Resolution tracker — auto-settle resolved Kalshi/Polymarket paper positions
        _kalshi_paper_broker = None
        _poly_paper_broker = None
        if config.paper_trading:
            # Kalshi paper broker (if Kalshi is configured)
            if config.kalshi_key_id and hasattr(data_bus, "_kalshi_source"):
                try:
                    from adapters.kalshi.paper import KalshiPaperBroker as _KPB

                    _kalshi_paper_broker = _KPB(store=_paper_store)
                    _brokers["kalshi_paper"] = _kalshi_paper_broker
                    _log.info("Kalshi paper broker enabled")
                except Exception as _kp_exc:
                    _log.warning("Kalshi paper broker setup failed: %s", _kp_exc)
            # Polymarket paper broker already set above as _poly_paper
            _poly_paper_broker = _brokers.get("polymarket_paper")

        _kalshi_client_ref = getattr(data_bus, "_kalshi_source", None)
        _kalshi_client_for_tracker = (
            _kalshi_client_ref._client
            if _kalshi_client_ref and hasattr(_kalshi_client_ref, "_client")
            else None
        )
        _poly_client_for_tracker = (
            getattr(_polymarket_source, "_client", None) if _polymarket_source else None
        )

        if _kalshi_client_for_tracker or _poly_client_for_tracker:
            from exits.resolution_tracker import ResolutionTracker

            _paper_store_for_tracker = _paper_store if config.paper_trading else None
            if _paper_store_for_tracker:
                _resolution_tracker = ResolutionTracker(
                    kalshi_client=_kalshi_client_for_tracker,
                    polymarket_client=_poly_client_for_tracker,
                    kalshi_paper_broker=_kalshi_paper_broker,
                    polymarket_paper_broker=_poly_paper_broker,
                    paper_store=_paper_store_for_tracker,
                    event_bus=event_bus,
                    poll_interval_seconds=600,
                )
                task_mgr.create_task(_resolution_tracker.run(), name="resolution_tracker")
                _log.info("ResolutionTracker started (poll interval: 600s)")

        # Start Fidelity file watcher as a background task
        from adapters.fidelity.watcher import FidelityFileWatcher

        _fidelity_watcher = FidelityFileWatcher(
            store=ext_store,
            import_dir=config.import_dir,
        )
        task_mgr.create_task(_fidelity_watcher.run(), name="fidelity_watcher")
        _log.info("FidelityFileWatcher started, watching '%s'", config.import_dir)

        # Start tournament cron after agents are loaded (uses runner.list_agents)
        if tournament_engine is not None:

            async def _run_tournament_cron():
                from croniter import croniter

                cron = croniter(
                    _learning_cfg.tournament.evaluate_cron, datetime.now(timezone.utc)
                )
                while True:
                    next_run = cron.get_next(datetime)
                    delay = (next_run - datetime.now(timezone.utc)).total_seconds()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    try:
                        await tournament_engine.evaluate_all()
                    except Exception as _te:
                        _log.warning("TournamentEngine.evaluate_all failed: %s", _te)

            task_mgr.create_task(_run_tournament_cron(), name="tournament_cron")
            _log.info(
                "TournamentEngine started (cron: %s)",
                _learning_cfg.tournament.evaluate_cron,
            )

        # --- Bittensor Integration ---
        from api.startup.integrations import setup_bittensor
        
        bittensor_enabled_runtime, bittensor_components = await setup_bittensor(
            config=config,
            db=db,
            data_bus=data_bus,
            event_bus=event_bus,
            signal_bus=signal_bus,
        )
        
        if bittensor_enabled_runtime:
            app.state.bittensor_store = bittensor_components["store"]
            app.state.bittensor_source = bittensor_components["source"]
            app.state.bittensor_adapter = bittensor_components["adapter"]
            app.state.bittensor_scheduler = bittensor_components["scheduler"]
            app.state.bittensor_evaluator = bittensor_components["evaluator"]
            app.state.bittensor_ranking_config = bittensor_components["ranking_config"]
            
            task_mgr.create_task(
                bittensor_components["scheduler"].run(),
                name="bittensor_scheduler"
            )
            task_mgr.create_task(
                bittensor_components["evaluator"].run(),
                name="bittensor_evaluator"
            )
            if bittensor_components.get("weight_setter"):
                app.state.bittensor_weight_setter = bittensor_components["weight_setter"]
                task_mgr.create_task(
                    bittensor_components["weight_setter"].run(),
                    name="bittensor_weight_setter"
                )
        elif config.bittensor_mock and not bittensor_enabled_runtime:
            from integrations.bittensor.mock_source import MockBittensorSource
            _bt_mock = MockBittensorSource(signal_bus=signal_bus)
            task_mgr.create_task(_bt_mock.start(), name="bittensor_mock")
            _log.info("MockBittensorSource started (real integration not active)")
        elif config.bittensor_mock and bittensor_enabled_runtime:
            _log.warning(
                "bittensor_mock=True ignored — real Bittensor integration is active"
            )

        app.state.bittensor_enabled_runtime = bittensor_enabled_runtime

    # Redis Streams event consumer (Phase 3: Redis Streams Event Bus)
    from events.consumer_streams import StreamsEventConsumer
    import redis.asyncio as aioredis

    redis_url = config.redis_url or "redis://127.0.0.1:6379"
    redis_client = await aioredis.from_url(redis_url, decode_responses=True)

    consumer = StreamsEventConsumer(
        redis=redis_client,
        stream="events",
        group="trading-service",
        consumer_name="worker-1"
    )

    # Register event handlers
    async def handle_trade_opened(data: dict):
        _log.info(f"TradeOpened event: {data}")
        # TODO: Add trading-specific logic (update dashboards, send notifications, etc.)

    async def handle_trade_closed(data: dict):
        _log.info(f"TradeClosed event: {data}")
        # TODO: Add trading-specific logic (update performance metrics, etc.)

    consumer.register("TradeOpened", handle_trade_opened)
    consumer.register("TradeClosed", handle_trade_closed)

    # Start consumer as background task
    task_mgr.create_task(consumer.start(), name="redis_streams_consumer")
    app.state.streams_consumer = consumer
    _log.info("Redis Streams consumer started")

    yield

    # --- Shutdown ---
    # Stop Redis Streams consumer first
    streams_consumer = getattr(app.state, "streams_consumer", None)
    if streams_consumer:
        await streams_consumer.stop()
        logging.getLogger(__name__).info("Redis Streams consumer stopped")

    task_mgr = getattr(app.state, "task_manager", None)
    if task_mgr:
        await task_mgr.shutdown()

    adapter_runner = getattr(app.state, "adapter_runner", None)
    if adapter_runner:
        await adapter_runner.stop()
    if runner:
        await runner.stop_all()
    if hasattr(app.state, "stream_manager"):
        await app.state.stream_manager.stop()

    # Disconnect all brokers
    for name, broker_obj in getattr(app.state, "brokers", {}).items():
        try:
            await broker_obj.connection.disconnect()
        except Exception as exc:
            _log.warning("Error disconnecting broker %s: %s", name, exc)

    # Journal indexer shutdown
    journal_indexer = getattr(app.state, "journal_indexer", None)
    if journal_indexer:
        await journal_indexer.stop()

    # Bittensor adapter close
    bt_adapter = getattr(app.state, "bittensor_adapter", None)
    if bt_adapter:
        try:
            await bt_adapter.close()
        except Exception as exc:
            _log.warning("Bittensor adapter close error: %s", exc)

    # Observability
    obs = getattr(app.state, "observability_emitter", None)
    if obs:
        obs.stop()

    # Redis connection (for authentication)
    redis = getattr(app.state, "redis", None)
    if redis:
        await redis.aclose()

    # Redis bridge
    rb = getattr(app.state, "redis_bridge", None)
    if rb:
        await rb.stop()


def create_app(
    broker: Broker | None = None,
    *,
    enable_agent_framework: bool = False,
    config: Config | None = None,
) -> FastAPI:
    app = FastAPI(title="Stock Trading API", version="0.1.0", lifespan=lifespan)
    if broker:
        set_broker(broker)
    app.state.broker = broker
    app.state.enable_agent_framework = enable_agent_framework
    app.state.config = config or load_config()

    app.include_router(health.router)
    app.include_router(accounts.router)
    app.include_router(market_data.router)
    app.include_router(orders.router)
    app.include_router(trades.router)
    app.include_router(agents.router)
    app.include_router(opportunities.router)
    app.include_router(risk.router)
    app.include_router(ws.router)
    app.include_router(analytics.router)
    app.include_router(tuning.router)
    from api.routes import strategy_analytics

    app.include_router(strategy_analytics.router)
    from api.routes import execution_analytics

    app.include_router(execution_analytics.router)
    app.include_router(experiments.router)
    from api.routes import leaderboard as leaderboard_route

    app.include_router(leaderboard_route.router)
    from api.routes import journal as journal_route

    app.include_router(journal_route.router)
    from api.routes import markets_browser, portfolio as portfolio_route

    app.include_router(markets_browser.router)
    app.include_router(portfolio_route.router)
    from api.routes import brief as brief_route, warroom as warroom_route

    app.include_router(brief_route.router)
    app.include_router(warroom_route.router)
    from api.routes.memory import router as memory_router

    app.include_router(memory_router)
    from api.routes.bittensor import router as bittensor_status_router

    app.include_router(bittensor_status_router)
    from api.routes import confidence_analytics as confidence_analytics_route

    app.include_router(confidence_analytics_route.router)
    from api.routes.strategy_health import router as strategy_health_router

    app.include_router(strategy_health_router)
    from api.routes.signal_features import router as signal_features_router

    app.include_router(signal_features_router)
    from api.routes import shadow as shadow_route

    app.include_router(shadow_route.router)

    @app.get("/privacy", include_in_schema=False)
    async def privacy_policy():
        from fastapi.responses import HTMLResponse

        return HTMLResponse("""<!DOCTYPE html>
<html><head><title>Privacy Policy — Remembr</title>
<style>body{font-family:system-ui;max-width:720px;margin:40px auto;padding:0 20px;line-height:1.6;color:#333}h1{border-bottom:1px solid #eee;padding-bottom:10px}</style>
</head><body>
<h1>Privacy Policy</h1>
<p><strong>Last updated:</strong> March 31, 2026</p>
<p>Remembr ("we", "us") operates the Remembr trading assistant accessible via WhatsApp. This policy describes how we handle information received through the WhatsApp Business API.</p>
<h2>Information We Collect</h2>
<p>When you message our WhatsApp number, we receive your phone number and message content. We also collect trading-related data you voluntarily provide (e.g., portfolio queries, trade requests).</p>
<h2>How We Use Information</h2>
<p>We use your information solely to operate the trading assistant: processing your requests, executing authorized trades, and sending notifications you have opted into.</p>
<h2>Data Storage &amp; Retention</h2>
<p>Message data is stored on our private infrastructure and is not shared with third parties. Conversation history is retained to provide context for the assistant and may be deleted upon request.</p>
<h2>Third-Party Services</h2>
<p>We integrate with brokerage APIs (e.g., Interactive Brokers, Alpaca) and AI services (Anthropic) to fulfill trading requests. These services receive only the minimum data necessary to process your request.</p>
<h2>Your Rights</h2>
<p>You may request deletion of your data at any time by messaging "delete my data" to the assistant or contacting us directly.</p>
<h2>Contact</h2>
<p>For privacy questions, contact the app administrator.</p>
</body></html>""")

    @app.exception_handler(BrokerConnectionError)
    async def broker_connection_error_handler(
        request: Request, exc: BrokerConnectionError
    ):
        return JSONResponse(
            status_code=503, content={"detail": str(exc)}, headers={"Retry-After": "5"}
        )

    @app.exception_handler(InvalidSymbol)
    async def invalid_symbol_handler(request: Request, exc: InvalidSymbol):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(InsufficientFunds)
    async def insufficient_funds_handler(request: Request, exc: InsufficientFunds):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(MarketClosed)
    async def market_closed_handler(request: Request, exc: MarketClosed):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(OrderRejected)
    async def order_rejected_handler(request: Request, exc: OrderRejected):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @app.exception_handler(BrokerError)
    async def broker_error_handler(request: Request, exc: BrokerError):
        return JSONResponse(
            status_code=502, content={"detail": "Broker error occurred"}
        )

    return app
