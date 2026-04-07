import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

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
from api.routes.learning import create_learning_router


async def _setup_trade_reflectors(
    *,
    config: Config,
    learning_cfg,
    learning_data,
    llm_client,
    remembr_sync,
    logger: logging.Logger,
):
    trade_reflector_factory = None
    global_reflector = None

    if not (
        (config.remembr_api_key or config.remembr_owner_token)
        and config.remembr_shared_api_key
        and learning_data.get("memory", {}).get("enabled", False)
    ):
        return trade_reflector_factory, global_reflector

    try:
        from remembr.client import AsyncRemembrClient
        from learning.memory_client import TradingMemoryClient
        from learning.trade_reflector import TradeReflector
        from api.routes.memory import register_shared_client

        mem_cfg = learning_cfg.memory
        shared_remembr = AsyncRemembrClient(
            agent_token=config.remembr_shared_api_key,
            base_url=config.remembr_base_url,
        )

        async def make_reflector(agent_name: str) -> TradeReflector:
            agent_token = config.remembr_api_key

            if remembr_sync and agent_name != "_global":
                try:
                    await remembr_sync.ensure_agents_registered([agent_name])
                    tokens = await remembr_sync.get_agent_tokens()
                    if agent_name in tokens:
                        agent_token = tokens[agent_name]
                        logger.debug("Using autonomous token for agent %s", agent_name)
                except Exception as exc:
                    logger.warning(
                        "Failed to get autonomous token for %s, falling back: %s",
                        agent_name,
                        exc,
                    )

            private_client = AsyncRemembrClient(
                agent_token=agent_token,
                base_url=config.remembr_base_url,
            )
            memory_client = TradingMemoryClient(
                private_client=private_client,
                shared_client=shared_remembr,
                ttl_days=mem_cfg.ttl_days,
            )

            return TradeReflector(
                memory_client=memory_client,
                deep_reflection_pnl_multiplier=mem_cfg.deep_reflection.pnl_multiplier,
                deep_reflection_loss_multiplier=mem_cfg.deep_reflection.loss_multiplier,
                llm=llm_client,
            )

        trade_reflector_factory = make_reflector

        shared_memory_client = TradingMemoryClient(
            private_client=shared_remembr,
            shared_client=shared_remembr,
            ttl_days=mem_cfg.ttl_days,
        )
        register_shared_client(shared_memory_client)
        logger.info("Agent memory system enabled (remembr.dev)")
    except Exception as exc:
        logger.warning("Memory system setup failed (continuing without it): %s", exc)
        return trade_reflector_factory, global_reflector

    if trade_reflector_factory:
        global_reflector = await trade_reflector_factory("_global")

    return trade_reflector_factory, global_reflector


def _setup_agent_runtime(
    *,
    app: FastAPI,
    config: Config,
    db,
    perf_store,
    agent_store,
    opp_store,
    notifier,
    risk_engine,
    broker,
    brokers,
    trade_store,
    data_bus,
    event_bus,
    signal_bus,
    emitter,
    trade_tracker,
    sizing_engine,
    exit_manager,
    exec_tracker,
    regime_filter,
    slippage_loop,
    global_reflector,
    signal_feature_capture,
    exec_cost_store,
    confidence_calibration_store,
    confidence_calibration_config,
    shadow_executor,
    journal_manager,
    trade_reflector_factory,
):
    from learning.strategy_health import StrategyHealthEngine
    from learning.strategy_health import StrategyHealthConfig as StrategyHealthConfig
    from storage.strategy_health import StrategyHealthStore as StrategyHealthStore
    from agents.router import OpportunityRouter, ConsensusRouter
    from agents.runner import AgentRunner
    from experiments.ab_test import get_experiment_manager

    health_store = StrategyHealthStore(db)
    health_config = StrategyHealthConfig.from_learning_config(
        getattr(app.state.learning_config, "strategy_health", None)
    )
    health_engine = StrategyHealthEngine(
        health_store=health_store,
        perf_store=perf_store,
        config=health_config,
    )
    app.state.health_engine = health_engine

    router = OpportunityRouter(
        store=opp_store,
        notifier=notifier,
        risk_engine=risk_engine,
        broker=broker,
        brokers=brokers,
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
        trade_reflector=global_reflector,
        health_engine=health_engine,
        signal_feature_capture=signal_feature_capture,
        execution_cost_store=exec_cost_store,
        confidence_calibration_store=confidence_calibration_store,
        confidence_calibration_config=confidence_calibration_config,
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
        emitter=emitter,
        signal_bus=signal_bus,
        health_engine=health_engine,
        trade_reflector_factory=trade_reflector_factory,
        agent_store=agent_store,
    )
    set_agent_runner(runner)
    app.state.agent_runner = runner

    base_router = router._target if hasattr(router, "_target") else router
    if hasattr(base_router, "_runner"):
        base_router._runner = runner

    return health_engine, router, runner


async def _setup_operator_services(
    *,
    app: FastAPI,
    config: Config,
    db,
    perf_store,
    runner,
    remembr_sync,
    task_mgr,
    logger: logging.Logger,
    pnl_store,
    opp_store,
    llm_client,
    journal_manager,
):
    from leaderboard.engine import LeaderboardEngine
    from journal.autopsy import AutopsyGenerator
    from journal.service import JournalService
    from brief.generator import BriefGenerator
    from warroom.engine import WarRoomEngine

    leaderboard_engine = LeaderboardEngine(
        perf_store=perf_store,
        runner=runner,
        db=db,
        remembr_sync=remembr_sync,
    )

    if remembr_sync and config.remembr_owner_token:

        async def _setup_remembr_team():
            try:
                agent_names = [a.name for a in runner.list_agents()]
                await remembr_sync.ensure_team_setup("stock-trading-api", agent_names)
            except Exception as exc:
                logger.warning("Autonomous team setup failed: %s", exc)

        task_mgr.create_task(_setup_remembr_team(), name="remembr_team_setup")

    app.state.leaderboard_engine = leaderboard_engine

    try:
        agent_names = [a.name for a in runner.list_agents()]
        seeded = await perf_store.seed_if_empty(agent_names)
        if seeded:
            logger.info(
                "Seeded %d agents with zero-state performance snapshots", seeded
            )
    except Exception as exc:
        logger.warning("Failed to seed performance snapshots: %s", exc)

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

    brief_generator = BriefGenerator(
        db=db,
        llm=llm_client,
    )
    app.state.brief_generator = brief_generator

    warroom_engine = WarRoomEngine(
        db=db,
        llm=llm_client,
    )
    app.state.warroom_engine = warroom_engine

    return leaderboard_engine, journal_service, brief_generator, warroom_engine


def _setup_tournament_engine(
    *,
    app: FastAPI,
    db,
    perf_store,
    notifier,
    runner,
    learning_cfg,
    llm_client,
):
    if not learning_cfg.tournament.enabled:
        return None

    from tournament.engine import TournamentEngine
    from tournament.store import TournamentStore
    from api.routes.tournament import create_tournament_router

    tournament_store = TournamentStore(db)
    tournament_engine = TournamentEngine(
        store=tournament_store,
        perf_store=perf_store,
        notifier=notifier,
        runner=runner,
        config=learning_cfg.tournament,
        llm=llm_client,
    )
    app.state.tournament_engine = tournament_engine
    app.include_router(create_tournament_router(tournament_engine))

    return tournament_engine


def _setup_whatsapp_routes(
    *,
    app: FastAPI,
    config: Config,
    wa_client,
    wa_numbers,
    broker,
    runner,
    opp_store,
    risk_engine,
    llm_client,
    ext_store,
    data_bus,
    leaderboard_engine,
    journal_service,
    brief_generator,
    warroom_engine,
    db,
    agent_store,
    logger: logging.Logger,
):
    from api.routes.test import create_test_router

    if not wa_client:
        app.include_router(create_test_router(wa_client=None, allowed_numbers=None))
        return

    from whatsapp.assistant import WhatsAppAssistant
    from whatsapp.webhook import create_webhook_router

    wa_remembr = None
    if config.remembr_api_key:
        try:
            from remembr.client import AsyncRemembrClient

            wa_remembr = AsyncRemembrClient(
                agent_token=config.remembr_api_key,
                base_url=config.remembr_base_url,
            )
            logger.info("WhatsApp assistant memory enabled via remembr.dev")
        except Exception as exc:
            logger.warning("Failed to init remembr.dev for WhatsApp: %s", exc)

    wa_assistant = WhatsAppAssistant(
        client=wa_client,
        broker=broker,
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
    wa_assistant.start_proactive(wa_numbers)

    app.include_router(
        create_test_router(
            wa_client=wa_client,
            allowed_numbers=config.whatsapp_allowed_numbers,
        )
    )


async def _setup_bittensor_integration(
    *,
    config,
    app,
    db,
    data_bus,
    event_bus,
    signal_bus,
    task_mgr,
    logger,
):
    """Set up Bittensor integration (real or mock) and wire components into app.state."""
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
            bittensor_components["scheduler"].run(), name="bittensor_scheduler"
        )
        task_mgr.create_task(
            bittensor_components["evaluator"].run(), name="bittensor_evaluator"
        )
        if bittensor_components.get("weight_setter"):
            app.state.bittensor_weight_setter = bittensor_components["weight_setter"]
            task_mgr.create_task(
                bittensor_components["weight_setter"].run(),
                name="bittensor_weight_setter",
            )
    elif config.bittensor_mock and not bittensor_enabled_runtime:
        from integrations.bittensor.mock_source import MockBittensorSource

        _bt_mock = MockBittensorSource(signal_bus=signal_bus)
        task_mgr.create_task(_bt_mock.start(), name="bittensor_mock")
        logger.info("MockBittensorSource started (real integration not active)")
    elif config.bittensor_mock and bittensor_enabled_runtime:
        logger.warning(
            "bittensor_mock=True ignored — real Bittensor integration is active"
        )

    app.state.bittensor_enabled_runtime = bittensor_enabled_runtime

    # --- Taoshi Bridge (reads official validator's position data) ---
    taoshi_root = config.taoshi_validator_root if hasattr(config, 'taoshi_validator_root') else None
    if not taoshi_root:
        import os
        taoshi_root = os.environ.get("STA_TAOSHI_VALIDATOR_ROOT", "")
    if taoshi_root:
        from integrations.bittensor.taoshi_bridge import TaoshiBridge

        bridge = TaoshiBridge(
            taoshi_root=taoshi_root,
            signal_bus=signal_bus,
            event_bus=event_bus,
            poll_interval=30.0,
        )
        app.state.taoshi_bridge = bridge
        task_mgr.create_task(bridge.run(), name="taoshi_bridge")
        logger.info("TaoshiBridge started (root=%s)", taoshi_root)
    else:
        logger.debug("TaoshiBridge disabled — STA_TAOSHI_VALIDATOR_ROOT not set")


def _setup_tournament_cron(task_mgr, tournament_engine):
    """Set up the tournament cron job to evaluate all tournaments periodically."""
    from croniter import croniter
    import asyncio
    from datetime import datetime
    import logging
    import json

    _log = logging.getLogger(__name__)

    async def _run_tournament_cron():
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
        "Tournament cron job started with schedule: %s",
        _learning_cfg.tournament.evaluate_cron,
    )


async def _load_and_start_agent_configs(
    *,
    agents_path,
    prompt_store,
    exit_manager,
    pnl_store,
    runner,
    logger: logging.Logger,
):
    from agents.config import load_agents_config, register_strategy
    from strategies.exit_monitor import ExitMonitorAgent as ExitMonitorAgent

    register_strategy(
        "exit_monitor",
        lambda config: ExitMonitorAgent(
            config=config,
            exit_manager=exit_manager,
            position_store=pnl_store,
        ),
    )

    if agents_path is None:
        logger.error(
            "CRITICAL: agents.yaml path is None, cannot load agent configurations"
        )
        agent_configs = []
    else:
        agent_configs = load_agents_config(str(agents_path), prompt_store=prompt_store)

    for agent in agent_configs:
        runner.register(agent)
        if agent.config.schedule in ("continuous", "cron"):
            await runner.start_agent(agent.name)

    await runner.start_polling(interval=60)

    return agent_configs


async def _setup_meta_agent(
    *,
    app: FastAPI,
    runner,
    signal_bus,
    data_bus,
    router,
    logger: logging.Logger,
    arb_coordinator=None,
):
    try:
        from agents.meta import MetaAgent
        from agents.signal_adapter import SignalAdapterRunner
        from agents.adapters.prediction_market import PredictionMarketAdapter
        from agents.models import AgentConfig as AgentConfig, ActionLevel as ActionLevel

        meta_cfg = AgentConfig(
            name="meta_agent",
            strategy="meta",
            schedule="continuous",
            interval=30,
            action_level=ActionLevel.NOTIFY,
            parameters={
                "boost_delta": 0.05,
                "max_cumulative_boost": 0.15,
                "boost_ttl_minutes": 15,
            },
        )
        meta_agent = MetaAgent(config=meta_cfg, runner=runner, signal_bus=signal_bus)
        runner.register(meta_agent)
        app.state.meta_agent = meta_agent
        router._meta_agent = meta_agent

        adapters = []
        if data_bus:
            adapters.append(PredictionMarketAdapter(data_bus=data_bus))
        if adapters:
            adapter_runner = SignalAdapterRunner(
                adapters=adapters, signal_bus=signal_bus
            )
            adapter_runner.start(intervals={"prediction_market": 300})
            app.state.adapter_runner = adapter_runner
            logger.info(
                "Signal adapter runner started with %d adapter(s)", len(adapters)
            )

        await runner.start_agent("meta_agent")
        logger.info("MetaAgent registered and started")

        if arb_coordinator:
            arb_coordinator._meta_agent = meta_agent
    except Exception as exc:
        logger.warning("MetaAgent setup failed (non-fatal): %s", exc)


async def _setup_stream_manager(
    *,
    app: FastAPI,
    streams,
    data_bus,
    event_bus,
    agent_configs,
    logger: logging.Logger,
):
    if not streams:
        return

    from streaming.manager import StreamManager

    stream_manager = StreamManager(
        streams=streams,
        data_bus=data_bus,
        event_bus=event_bus,
    )
    await stream_manager.start()

    all_symbols: set[str] = set()
    for agent in agent_configs:
        universe = getattr(agent.config, "universe", [])
        if isinstance(universe, list):
            all_symbols.update(universe)
    if all_symbols:
        await stream_manager.subscribe(list(all_symbols))

    app.state.stream_manager = stream_manager
    logger.info(
        "StreamManager started with %d streams, %d symbols",
        len(streams),
        len(all_symbols),
    )


def _setup_tournament_cron(task_mgr, tournament_engine):
    """Set up the tournament cron job to evaluate all tournaments periodically."""
    from croniter import croniter
    import asyncio
    from datetime import datetime
    import logging
    import json

    _log = logging.getLogger(__name__)

    async def _run_tournament_cron():
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
        "Tournament cron job started with schedule: %s",
        _learning_cfg.tournament.evaluate_cron,
    )


def _setup_resolution_tracker(
    *,
    config: Config,
    data_bus,
    polymarket_source,
    paper_store,
    brokers,
    event_bus,
    task_mgr,
    logger: logging.Logger,
):
    kalshi_paper_broker = None
    polymarket_paper_broker = None

    if config.paper_trading:
        if config.kalshi_key_id and hasattr(data_bus, "_kalshi_source"):
            try:
                from adapters.kalshi.paper import KalshiPaperBroker

                kalshi_paper_broker = KalshiPaperBroker(store=paper_store)
                brokers["kalshi_paper"] = kalshi_paper_broker
                logger.info("Kalshi paper broker enabled")
            except Exception as exc:
                logger.warning("Kalshi paper broker setup failed: %s", exc)

        polymarket_paper_broker = brokers.get("polymarket_paper")

    kalshi_client_ref = getattr(data_bus, "_kalshi_source", None)
    kalshi_client_for_tracker = (
        kalshi_client_ref._client
        if kalshi_client_ref and hasattr(kalshi_client_ref, "_client")
        else None
    )
    polymarket_client_for_tracker = (
        getattr(polymarket_source, "_client", None) if polymarket_source else None
    )

    if not (kalshi_client_for_tracker or polymarket_client_for_tracker):
        return None

    paper_store_for_tracker = paper_store if config.paper_trading else None
    if not paper_store_for_tracker:
        return None

    from exits.resolution_tracker import ResolutionTracker

    resolution_tracker = ResolutionTracker(
        kalshi_client=kalshi_client_for_tracker,
        polymarket_client=polymarket_client_for_tracker,
        kalshi_paper_broker=kalshi_paper_broker,
        polymarket_paper_broker=polymarket_paper_broker,
        paper_store=paper_store_for_tracker,
        event_bus=event_bus,
        poll_interval_seconds=600,
    )
    task_mgr.create_task(resolution_tracker.run(), name="resolution_tracker")
    logger.info("ResolutionTracker started (poll interval: 600s)")

    return resolution_tracker


async def _start_redis_streams_consumer(
    *,
    app: FastAPI,
    config: Config,
    task_mgr,
    logger: logging.Logger,
    llm_client,
):
    from events.consumer_streams import StreamsEventConsumer
    import redis.asyncio as aioredis

    redis_url = config.redis_url or "redis://127.0.0.1:6379"
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    consumer = StreamsEventConsumer(
        redis=redis_client,
        stream="events",
        group="trading-service",
        consumer_name="worker-1",
        event_bus=getattr(app.state, "event_bus", None),
    )

    from integrations.memory.consolidator import MemoryConsolidator
    consolidator = MemoryConsolidator(llm_client=llm_client, redis_client=redis_client)

    async def handle_trade_opened(data: dict):
        logger.info("TradeOpened event: %s", data)

    async def handle_trade_closed(data: dict):
        logger.info("TradeClosed event: %s", data)

    async def handle_memory_consolidation_requested(data: dict):
        await consolidator.consolidate(data)

    consumer.register("TradeOpened", handle_trade_opened)
    consumer.register("TradeClosed", handle_trade_closed)
    consumer.register("memory.consolidation.requested", handle_memory_consolidation_requested)

    task_mgr.create_task(consumer.start(), name="redis_streams_consumer")
    app.state.streams_consumer = consumer
    logger.info("Redis Streams consumer started")


async def _shutdown_app_state(*, app: FastAPI, runner, logger: logging.Logger):
    streams_consumer = getattr(app.state, "streams_consumer", None)
    if streams_consumer:
        await streams_consumer.stop()
        logger.info("Redis Streams consumer stopped")

    task_manager = getattr(app.state, "task_manager", None)
    if task_manager:
        await task_manager.shutdown()

    adapter_runner = getattr(app.state, "adapter_runner", None)
    if adapter_runner:
        await adapter_runner.stop()
    if runner:
        logger.info("Stopping agent runner...")
        await runner.stop_all()
        logger.info("Agent runner stopped.")
    
    if hasattr(app.state, "stream_manager"):
        logger.info("Stopping stream manager...")
        await app.state.stream_manager.stop()
        logger.info("Stream manager stopped.")

    for name, broker_obj in getattr(app.state, "brokers", {}).items():
        try:
            logger.info("Disconnecting broker %s...", name)
            await broker_obj.connection.disconnect()
            logger.info("Broker %s disconnected.", name)
        except Exception as exc:
            logger.warning("Error disconnecting broker %s: %s", name, exc)

    journal_indexer = getattr(app.state, "journal_indexer", None)
    if journal_indexer:
        logger.info("Stopping journal indexer...")
        await journal_indexer.stop()
        logger.info("Journal indexer stopped.")

    bt_adapter = getattr(app.state, "bittensor_adapter", None)
    if bt_adapter:
        try:
            logger.info("Closing bittensor adapter...")
            await bt_adapter.close()
            logger.info("Bittensor adapter closed.")
        except Exception as exc:
            logger.warning("Bittensor adapter close error: %s", exc)

    obs = getattr(app.state, "observability_emitter", None)
    if obs:
        logger.info("Stopping observability emitter...")
        obs.stop()
        logger.info("Observability emitter stopped.")

    redis_bridge = getattr(app.state, "redis_bridge", None)
    if redis_bridge:
        logger.info("Stopping redis bridge...")
        await redis_bridge.stop()
        logger.info("Redis bridge stopped.")

    redis = getattr(app.state, "redis", None)
    if redis:
        logger.info("Closing redis...")
        await redis.aclose()
        logger.info("Redis closed.")


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
        from utils.config_loader import ConfigLoader

        _log = logging.getLogger(__name__)
        _app_root = pathlib.Path(__file__).resolve().parent.parent

        config_loader = ConfigLoader(app_root=_app_root)

        # --- Fail-fast config validation (before DB init or broker connect) ---
        from api.startup.config_validation import validate_configs

        _validated = await validate_configs(config, config_loader)
        _learning_cfg = _validated.learning_cfg
        _learning_data = _validated.learning_data
        _risk_path_str = _validated.risk_path_str
        _risk_data = _validated.risk_data
        _agents_data = _validated.agents_data
        _agents_path_str = _validated.agents_path_str
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
        from data.events import EventBus
        from experiments.ab_test import get_experiment_manager
        from execution.shadow import ShadowExecutor, ShadowOutcomeResolver

        event_bus = EventBus()
        signal_bus = SignalBus()
        set_event_bus(event_bus)
        app.state.event_bus = event_bus

        # --- Redis Connection + Signal Bridge ---
        from api.startup.redis import setup_redis

        await setup_redis(config=config, event_bus=event_bus, app_state=app.state)

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
        task_mgr.create_task(
            _shadow_outcome_resolver_loop(), name="shadow_outcome_resolver"
        )

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
                    name="rss_news_source",
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
                    task_mgr.create_task(
                        _ws_feed.run(_token_ids), name="polymarket_ws_feed"
                    )
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

        _trade_reflector_factory, _global_reflector = await _setup_trade_reflectors(
            config=config,
            learning_cfg=_learning_cfg,
            learning_data=_learning_data,
            llm_client=llm_client,
            remembr_sync=remembr_sync,
            logger=_log,
        )

        health_engine, router, runner = _setup_agent_runtime(
            app=app,
            config=config,
            db=db,
            perf_store=perf_store,
            agent_store=agent_store,
            opp_store=opp_store,
            notifier=notifier,
            risk_engine=risk_engine,
            broker=broker,
            brokers=_brokers,
            trade_store=trade_store,
            data_bus=data_bus,
            event_bus=event_bus,
            signal_bus=signal_bus,
            emitter=_emitter,
            trade_tracker=trade_tracker,
            sizing_engine=sizing_engine,
            exit_manager=exit_manager,
            exec_tracker=exec_tracker,
            regime_filter=regime_filter,
            slippage_loop=slippage_loop,
            global_reflector=_global_reflector,
            signal_feature_capture=_sf_capture,
            exec_cost_store=exec_cost_store,
            confidence_calibration_store=_cc_store,
            confidence_calibration_config=_cc_cfg,
            shadow_executor=shadow_executor,
            journal_manager=journal_manager,
            trade_reflector_factory=_trade_reflector_factory,
        )

        (
            leaderboard_engine,
            journal_service,
            brief_generator,
            warroom_engine,
        ) = await _setup_operator_services(
            app=app,
            config=config,
            db=db,
            perf_store=perf_store,
            runner=runner,
            remembr_sync=remembr_sync,
            task_mgr=task_mgr,
            logger=_log,
            pnl_store=pnl_store,
            opp_store=opp_store,
            llm_client=llm_client,
            journal_manager=journal_manager,
        )

        # Tournament Engine (optional — only if learning config has tournament.enabled)
        from datetime import datetime, timezone

        tournament_engine = _setup_tournament_engine(
            app=app,
            db=db,
            perf_store=perf_store,
            notifier=notifier,
            runner=runner,
            learning_cfg=_learning_cfg,
            llm_client=llm_client,
        )

        _setup_whatsapp_routes(
            app=app,
            config=config,
            wa_client=wa_client,
            wa_numbers=wa_numbers,
            broker=broker,
            runner=runner,
            opp_store=opp_store,
            risk_engine=risk_engine,
            llm_client=llm_client,
            ext_store=ext_store,
            data_bus=data_bus,
            leaderboard_engine=leaderboard_engine,
            journal_service=journal_service,
            brief_generator=brief_generator,
            warroom_engine=warroom_engine,
            db=db,
            agent_store=agent_store,
            logger=_log,
        )

        # NOTE: load_agents_config() still re-reads agents.yaml from disk (line 182 in agents/config.py).
        # To fully eliminate duplicate reads, we would need to refactor load_agents_config() to accept
        # parsed data instead of a path, which is outside the scope of this task.
        agent_configs = await _load_and_start_agent_configs(
            agents_path=_agents_path_str,
            prompt_store=prompt_store,
            exit_manager=exit_manager,
            pnl_store=pnl_store,
            runner=runner,
            logger=_log,
        )

        await _setup_meta_agent(
            app=app,
            runner=runner,
            signal_bus=signal_bus,
            data_bus=data_bus,
            router=router,
            logger=_log,
            arb_coordinator=locals().get("_arb_coordinator"),
        )

        await _setup_stream_manager(
            app=app,
            streams=_streams,
            data_bus=data_bus,
            event_bus=event_bus,
            agent_configs=agent_configs,
            logger=_log,
        )

        _setup_resolution_tracker(
            config=config,
            data_bus=data_bus,
            polymarket_source=_polymarket_source,
            paper_store=_paper_store,
            brokers=_brokers,
            event_bus=event_bus,
            task_mgr=task_mgr,
            logger=_log,
        )

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
        await _setup_bittensor_integration(
            config=config,
            app=app,
            db=db,
            data_bus=data_bus,
            event_bus=event_bus,
            signal_bus=signal_bus,
            task_mgr=task_mgr,
            logger=_log,
        )

    await _start_redis_streams_consumer(
        app=app,
        config=config,
        task_mgr=task_mgr,
        logger=_log,
        llm_client=llm_client,
    )

    yield

    await _shutdown_app_state(app=app, runner=runner, logger=_log)


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
    from api.routes import bittensor as bittensor_route

    app.include_router(bittensor_route.router)
    from api.routes.memory import router as memory_router

    app.include_router(memory_router)
    from api.routes import confidence_analytics as confidence_analytics_route

    app.include_router(confidence_analytics_route.router)
    from api.routes.strategy_health import router as strategy_health_router

    app.include_router(strategy_health_router)
    from api.routes.signal_features import router as signal_features_router

    app.include_router(signal_features_router)
    from api.routes import shadow as shadow_route

    app.include_router(shadow_route.router)

    from api.startup.error_handlers import register_error_handlers

    register_error_handlers(app)

    return app
