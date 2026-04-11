from __future__ import annotations
import asyncio
import logging
import pathlib
import yaml
import os
from typing import TYPE_CHECKING, Any, Dict, Optional, List

from config import Config
from data.events import EventBus
from data.signal_bus import SignalBus
from llm.client import LLMClient
from storage.db import create_db
from api.deps import (
    set_broker,
    set_agent_runner,
    set_risk_engine,
    set_opportunity_store,
    set_trade_store,
    set_event_bus,
)

if TYPE_CHECKING:
    from fastapi import FastAPI
    from broker.interfaces import Broker
    from agents.runner import AgentRunner
    from risk.engine import RiskEngine
    from data.bus import DataBus
    from storage.opportunities import OpportunityStore
    from storage.trades import TradeStore

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    Manages the lifecycle and dependency injection of all core services.
    Refactored from app.py to decouple startup logic from the FastAPI lifespan.
    """

    def __init__(self, settings: Config):
        self.settings = settings
        self.app_root = pathlib.Path(__file__).resolve().parent.parent

        # Infrastructure
        self.db: Any = None
        self.event_bus = EventBus()
        self.signal_bus = SignalBus()
        self.llm_client: Optional[LLMClient] = None
        self.redis_bridge: Any = None
        self.emitter: Any = None

        # Storage
        self.opp_store: Optional[OpportunityStore] = None
        self.trade_store: Optional[TradeStore] = None
        self.pnl_store: Any = None
        self.perf_store: Any = None
        self.agent_store: Any = None
        self.ext_store: Any = None
        self.shadow_store: Any = None
        self.sf_store: Any = None
        self.cc_store: Any = None

        # Functional Services
        self.broker: Optional[Broker] = None
        self.all_brokers: Dict[str, Broker] = {}
        self.data_bus: Optional[DataBus] = None
        self.risk_engine: Optional[RiskEngine] = None
        self.runner: Optional[AgentRunner] = None
        self.sizing_engine: Any = None
        self.shadow_executor: Any = None
        self.shadow_outcome_resolver: Any = None

        # Intelligence & Memory
        self.journal_manager: Any = None
        self.journal_indexer: Any = None
        self.journal_service: Any = None
        self.remembr_sync: Any = None
        self.meta_agent: Any = None

        # Interface Services
        self.wa_assistant: Any = None
        self.brief_generator: Any = None
        self.warroom_engine: Any = None
        self.tournament_engine: Any = None

        # State & Tasks
        self.tasks: List[asyncio.Task] = []
        self.services: Dict[str, Any] = {}
        self.learning_config: Any = None

    def _resolve_path(self, name: str) -> str:
        for candidate in [
            f"/app/{name}",
            name,
            str(self.app_root / name),
        ]:
            if os.path.isfile(candidate):
                return candidate
        return str(self.app_root.parent / name)

    async def bootstrap(self):
        """Phase 1: Essential infrastructure bootstrap."""
        from utils.telemetry import setup_telemetry

        setup_telemetry()

        await self._load_learning_config()

        set_event_bus(self.event_bus)
        self.db = await create_db(self.settings)

        self.llm_client = LLMClient(
            anthropic_key=self.settings.anthropic_api_key,
            groq_key=self.settings.groq_api_key,
            ollama_url=self.settings.ollama_base_url,
        )

        if self.settings.redis_url:
            try:
                from data.redis_bridge import RedisSignalBridge

                node_id = "oracle" if self.settings.worker_mode else "primary"
                self.redis_bridge = RedisSignalBridge(
                    self.event_bus, self.settings.redis_url, node_id
                )
                await self.redis_bridge.start()
            except Exception as e:
                logger.warning(f"RedisSignalBridge failed: {e}")

        logger.info("ServiceContainer: Infrastructure bootstrap complete")

    async def _load_learning_config(self):
        from learning.config import LearningConfig

        l_path = self._resolve_path("learning.yaml")
        if os.path.isfile(l_path):
            with open(l_path) as f:
                data = yaml.safe_load(f)
            self.learning_config = LearningConfig(**data)
        else:
            self.learning_config = LearningConfig(
                memory={"enabled": False}, strategy_health={"enabled": False}
            )

    async def start_profile(self, app: FastAPI):
        """Phase 2: Full service initialization based on Node Role."""
        # 1. Base Storage
        await self._init_base_storage()

        # 2. Broker (Primary only)
        if not self.settings.worker_mode:
            await self._init_multi_brokers()

        # 3. Data Bus & Sources
        await self._init_data_bus()

        # 4. Intelligence & Memory
        await self._init_intelligence_system()

        # 5. Pipeline (Primary only)
        if not self.settings.worker_mode:
            await self._init_execution_pipeline()

        # 6. Agent Framework
        await self._init_agent_framework()

        # 7. Final Interfaces (Primary only)
        if not self.settings.worker_mode:
            await self._init_interfaces(app)

        # 8. Bittensor (Optional)
        if self.settings.bittensor_enabled:
            await self._init_bittensor()

    async def _init_base_storage(self):
        from storage.opportunities import OpportunityStore
        from storage.trades import TradeStore
        from storage.performance import PerformanceStore
        from storage.pnl import TrackedPositionStore
        from storage.agent_registry import AgentStore
        from storage.external import ExternalPortfolioStore
        from storage.shadow import ShadowExecutionStore
        from storage.signal_features import SignalFeatureStore
        from storage.confidence_calibration import ConfidenceCalibrationStore

        self.opp_store = OpportunityStore(self.db)
        self.trade_store = TradeStore(self.db)
        self.perf_store = PerformanceStore(self.db)
        self.pnl_store = TrackedPositionStore(self.db)
        self.agent_store = AgentStore(self.db)
        self.ext_store = ExternalPortfolioStore(self.db)
        self.shadow_store = ShadowExecutionStore(self.db)
        self.sf_store = SignalFeatureStore(self.db)
        self.cc_store = ConfidenceCalibrationStore(self.db)

        set_opportunity_store(self.opp_store)
        set_trade_store(self.trade_store)

    async def _init_multi_brokers(self):
        from adapters.paper.broker import SimulatedBroker
        from storage.paper import PaperStore

        if self.settings.paper_trading:
            _ps = PaperStore(self.db)
            await _ps.init_tables()
            _initial = self.settings.paper_trading_initial_balance
            await self.db.execute(
                "INSERT OR REPLACE INTO paper_accounts (account_id, net_liquidation, buying_power, cash, maintenance_margin) VALUES ('PAPER', ?, ?, ?, 0.0)",
                (_initial, _initial, _initial),
            )
            await self.db.commit()
            self.broker = SimulatedBroker(store=_ps, initial_balance=_initial)
            await self.broker.connection.connect()
            self.all_brokers["paper"] = self.broker
            set_broker(self.broker)

    async def _init_data_bus(self):
        from data.bus import DataBus
        from data.sources.yahoo import YahooFinanceSource
        from data.sources.broker_source import BrokerSource

        sources = [YahooFinanceSource()]
        if self.broker and not self.settings.paper_trading:
            sources.append(BrokerSource(self.broker))

        if self.settings.massive_key:
            try:
                from data.massive import MassiveClient
                from data.massive_source import MassiveDataSource

                _sources = [
                    MassiveDataSource(MassiveClient(api_key=self.settings.massive_key)),
                    *sources,
                ]
                sources = _sources
            except Exception as e:
                logger.warning(f"Massive setup failed: {e}")

        _acc_id = "PAPER" if self.settings.paper_trading else ""
        self.data_bus = DataBus(
            sources=sources,
            broker=self.broker,
            trade_store=self.trade_store,
            account_id=_acc_id,
        )
        self.data_bus._llm_client = self.llm_client

        if self.settings.paper_trading and hasattr(
            self.broker, "_market_data_provider"
        ):
            self.broker._market_data_provider._data_bus = self.data_bus

    async def _init_intelligence_system(self):
        from journal.manager import JournalManager
        from remembr.client import AsyncRemembrClient
        from leaderboard.remembr_sync import RemembrArenaSync

        # Arena Sync
        reg_token = (
            self.settings.remembr_owner_token or self.settings.remembr_agent_token
        )
        if reg_token:
            self.remembr_sync = RemembrArenaSync(
                token=reg_token, db=self.db, base_url=self.settings.remembr_base_url
            )

        # Journal
        token = self.settings.remembr_private_token
        if token:
            _client = AsyncRemembrClient(
                agent_token=token, base_url=self.settings.remembr_base_url
            )
            if self.settings.journal_index_enabled:
                from journal.indexer import JournalIndexer

                self.journal_indexer = JournalIndexer(
                    self.event_bus, _client, gpu_enabled=self.settings.gpu_enabled
                )
                await self.journal_indexer.start()

            self.journal_manager = JournalManager(
                client=_client,
                event_bus=self.event_bus,
                indexer=self.journal_indexer,
                oracle_url=self.settings.oracle_url,
            )

    async def _init_execution_pipeline(self):
        from risk.config import load_risk_config
        from exits.manager import ExitManager
        from execution.tracker import ExecutionTracker
        from execution.feedback import SlippageFeedbackLoop
        from sizing.engine import SizingEngine
        from execution.shadow import ShadowExecutor, ShadowOutcomeResolver
        from learning.signal_features import SignalFeatureCapture

        self.sizing_engine = SizingEngine(perf_store=self.perf_store)

        from storage.portfolio_state import PortfolioStateStore

        portfolio_state_store = PortfolioStateStore(self.db)
        await portfolio_state_store.initialize()

        self.risk_engine = load_risk_config(
            self._resolve_path("risk.yaml"),
            perf_store=self.perf_store,
            agent_store=self.agent_store,
            settings=self.settings,
            journal_manager=self.journal_manager,
            portfolio_state_store=portfolio_state_store,
        )
        set_risk_engine(self.risk_engine)

        from storage.exit_rules import ExitRuleStore

        self.services["exit_manager"] = ExitManager(store=ExitRuleStore(self.db))
        await self.services["exit_manager"].load_rules()

        from storage.execution_quality import ExecutionQualityStore

        _eqs = ExecutionQualityStore(self.db)
        self.services["exec_tracker"] = ExecutionTracker(store=_eqs)
        self.services["slippage_loop"] = SlippageFeedbackLoop(
            tracker=self.services["exec_tracker"],
            perf_store=self.perf_store,
            agent_store=self.agent_store,
        )

        self.shadow_executor = ShadowExecutor(
            store=self.shadow_store, data_bus=self.data_bus
        )
        self.shadow_outcome_resolver = ShadowOutcomeResolver(
            store=self.shadow_store, data_bus=self.data_bus
        )
        self.tasks.append(asyncio.create_task(self._shadow_resolver_loop()))

        self.services["sf_capture"] = SignalFeatureCapture(
            store=self.sf_store, data_bus=self.data_bus
        )

    async def _shadow_resolver_loop(self):
        while True:
            try:
                await self.shadow_outcome_resolver.resolve_due(limit=25)
            except Exception as e:
                logger.warning(f"Shadow resolver failed: {e}")
            await asyncio.sleep(60)

    async def _init_agent_framework(self):
        from agents.runner import AgentRunner
        from agents.router import OpportunityRouter
        from agents.config import load_agents_config
        from learning.prompt_store import SqlPromptStore
        from learning.strategy_health import StrategyHealthEngine, StrategyHealthConfig
        from storage.strategy_health import StrategyHealthStore
        from notifications.log_notifier import LogNotifier
        from notifications.composite import CompositeNotifier
        from notifications.slack import SlackNotifier

        # Notifier
        _notifiers = [LogNotifier()]
        _api_base = f"http://{self.settings.api_host}:{self.settings.api_port}"
        if self.settings.slack_webhook_url:
            _notifiers.append(
                SlackNotifier(
                    self.settings.slack_webhook_url,
                    _api_base,
                    api_key=self.settings.api_key,
                )
            )
        self.services["notifier"] = CompositeNotifier(_notifiers)

        # Health Engine
        _sh_store = StrategyHealthStore(self.db)
        _sh_cfg = StrategyHealthConfig.from_learning_config(
            getattr(self.learning_config, "strategy_health", None)
        )
        health_engine = StrategyHealthEngine(
            health_store=_sh_store, perf_store=self.perf_store, config=_sh_cfg
        )

        # Router
        router = OpportunityRouter(
            store=self.opp_store,
            notifier=self.services["notifier"],
            risk_engine=self.risk_engine,
            broker=self.broker,
            trade_store=self.trade_store,
            data_bus=self.data_bus,
            event_bus=self.event_bus,
            sizing_engine=self.sizing_engine,
            exit_manager=self.services.get("exit_manager"),
            execution_tracker=self.services.get("exec_tracker"),
            health_engine=health_engine,
            journal_manager=self.journal_manager,
        )

        self.runner = AgentRunner(
            data_bus=self.data_bus,
            router=router,
            event_bus=self.event_bus,
            signal_bus=self.signal_bus,
            health_engine=health_engine,
            agent_store=self.agent_store,
        )
        set_agent_runner(self.runner)

        # Load agents
        _path = self._resolve_path(
            self.settings.agents_config
            or ("agents.paper.yaml" if self.settings.paper_trading else "agents.yaml")
        )
        agents = load_agents_config(_path, prompt_store=SqlPromptStore(self.db))
        for a in agents:
            self.runner.register(a)
        await self.runner.start_polling(interval=60)

    async def _init_interfaces(self, app: FastAPI):
        pass

    async def _init_bittensor(self):
        pass

    async def shutdown(self):
        logger.info("ServiceContainer: Shutting down...")
        if self.runner:
            await self.runner.stop_polling()
        if self.journal_indexer:
            await self.journal_indexer.stop()
        if self.redis_bridge:
            await self.redis_bridge.stop()
        if self.db:
            await self.db.close()
        for t in self.tasks:
            t.cancel()
        logger.info("Shutdown complete")
