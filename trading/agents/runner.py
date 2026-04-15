# agents/runner.py
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from agents.base import Agent
from agents.models import AgentInfo, AgentStatus, Opportunity

from agents.models import AgentSignal
from data.signal_bus import SignalBus

if TYPE_CHECKING:
    from agents.router import OpportunityRouter
    from data.bus import DataBus
    from data.events import EventBus
    from learning.strategy_health import StrategyHealthEngine
    from learning.trade_reflector import TradeReflector
    from storage.agent_registry import AgentStore

from opentelemetry import trace
from utils.telemetry import get_tracer

logger = logging.getLogger(__name__)

tracer = get_tracer(__name__)


class AgentRunner:
    async def _record_thought(
        self,
        agent_name: str,
        symbol: str,
        action: Any,
        score: float,
        rules: list,
        memories: list,
    ):
        if not self._db:
            return
        from models.thought import ThoughtRecord
        import uuid
        import json

        record = ThoughtRecord(
            id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            agent_name=agent_name,
            symbol=symbol,
            action=action,
            conviction_score=score,
            rule_evaluations=rules,
            memory_context=memories,
        )
        try:
            if hasattr(self._db, "add"):
                self._db.add(record)
                await self._db.commit()
            else:
                query = """
                    INSERT INTO thought_records 
                    (id, timestamp, agent_name, symbol, action, conviction_score, rule_evaluations, memory_context)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """
                await self._db.execute(
                    query,
                    (
                        str(record.id),
                        record.timestamp.isoformat(),
                        record.agent_name,
                        record.symbol,
                        record.action.value,
                        record.conviction_score,
                        json.dumps(record.rule_evaluations),
                        json.dumps(record.memory_context),
                    ),
                )
        except Exception as e:
            logger.error(f"Failed to record thought for {agent_name}: {e}")

    def __init__(
        self,
        data_bus: DataBus,
        router: OpportunityRouter,
        event_bus: EventBus | None = None,
        emitter: Any | None = None,
        signal_bus: SignalBus | None = None,
        health_engine: StrategyHealthEngine | None = None,
        trade_reflector_factory: Callable[[str], Any] | None = None,
        agent_store: AgentStore | None = None,
        session_bias_generator: Any | None = None,
        db: Any | None = None,
        tradingview_fetcher: Any | None = None,
        max_concurrent_scans: int = 5,
        default_scan_timeout: float = 120.0,
    ) -> None:
        self._data_bus = data_bus
        self._router = router
        self._event_bus = event_bus
        self._emitter = emitter
        self._signal_bus = signal_bus or SignalBus()
        self._health_engine = health_engine
        self._trade_reflector_factory = trade_reflector_factory
        self._agent_store = agent_store
        self._session_bias_generator = session_bias_generator
        self._db = db
        self._tv_fetcher = tradingview_fetcher
        self._redis = getattr(event_bus, "_redis", None) if event_bus else None
        self._reflectors: dict[str, TradeReflector] = {}
        self._agent_memory: Any | None = None
        if self._event_bus:
            self._signal_bus.subscribe(self._forward_signal_to_events)
        self._agents: dict[str, Agent] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._status: dict[str, AgentStatus] = {}
        self._last_run: dict[str, datetime] = {}
        self._error_counts: dict[str, int] = {}
        self._last_errors: dict[str, str | None] = {}
        self._cycle_counts: dict[str, int] = {}
        self._poll_task: asyncio.Task | None = None
        # Snapshot of registry configs for change detection (warm-restart)
        self._registry_configs: dict[str, dict] = {}
        self._scan_semaphore = asyncio.Semaphore(max_concurrent_scans)
        self._default_scan_timeout = default_scan_timeout

    def set_agent_memory(self, agent_memory: Any) -> None:
        """Inject unified AgentMemory into the runner and all registered agents."""
        self._agent_memory = agent_memory
        for agent in self._agents.values():
            agent.agent_memory = agent_memory

    def register(self, agent: Agent) -> None:
        self._agents[agent.name] = agent
        self._status[agent.name] = AgentStatus.STOPPED
        self._error_counts[agent.name] = 0
        self._last_errors[agent.name] = None
        self._cycle_counts[agent.name] = 0

    def list_agents(self) -> list[AgentInfo]:
        return [
            AgentInfo(
                name=name,
                description=agent.description,
                status=self._status[name],
                config=agent.config,
                last_run=self._last_run.get(name),
                error_count=self._error_counts.get(name, 0),
                last_error=self._last_errors.get(name),
            )
            for name, agent in self._agents.items()
        ]

    def get_agent(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def get_agent_info(self, name: str) -> AgentInfo | None:
        agent = self._agents.get(name)
        if not agent:
            return None
        return AgentInfo(
            name=name,
            description=agent.description,
            status=self._status[name],
            config=agent.config,
            last_run=self._last_run.get(name),
            error_count=self._error_counts.get(name, 0),
            last_error=self._last_errors.get(name),
        )

    async def update_agent_shadow_mode(
        self, agent_name: str, shadow_mode: bool
    ) -> bool:
        """Update an agent's shadow_mode at runtime.

        Returns True if agent was updated, False if agent not found.
        """
        agent = self._agents.get(agent_name)
        if agent is None:
            return False

        # Update the config
        agent.config.shadow_mode = shadow_mode

        # Log the change
        logger.info(f"Updated shadow_mode={shadow_mode} for agent '{agent_name}'")

        return True

    async def _forward_signal_to_events(self, signal: AgentSignal) -> None:
        if self._event_bus:
            await self._event_bus.publish(
                "agent_signal",
                {
                    "source_agent": signal.source_agent,
                    "target_agent": signal.target_agent,
                    "signal_type": signal.signal_type,
                    "payload": signal.payload,
                    "expires_at": signal.expires_at.isoformat(),
                    "timestamp": signal.timestamp.isoformat(),
                },
            )

    async def start_agent(self, name: str) -> None:
        agent = self._agents.get(name)
        if not agent:
            raise KeyError(f"Unknown agent: {name}")
        if self._status[name] == AgentStatus.RUNNING:
            return
        agent.signal_bus = self._signal_bus
        # Prime L0+L1 context (no cold starts)
        if hasattr(agent, "_prompt_store") and agent._prompt_store:
            await agent._prompt_store.generate_agent_context(
                agent_name=name,
                agent_config=agent._config,
            )
        await agent.setup()
        self._status[name] = AgentStatus.RUNNING
        schedule = agent.config.schedule
        if schedule == "continuous":
            self._tasks[name] = asyncio.create_task(self._run_continuous(agent))
        elif schedule == "cron":
            self._tasks[name] = asyncio.create_task(self._run_cron(agent))

    async def stop_agent(self, name: str, graceful: bool = True) -> None:
        agent = self._agents.get(name)
        if not agent:
            raise KeyError(f"Unknown agent: {name}")

        task = self._tasks.get(name)
        if task:
            if graceful:
                logger.info("Gracefully draining agent '%s'...", name)
                agent._draining = True
                # Wait up to 30s for the current cycle to finish
                try:
                    await asyncio.wait_for(task, timeout=30.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    logger.warning(
                        "Agent '%s' did not drain in time, cancelling task", name
                    )
                    task.cancel()
            else:
                task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                self._tasks.pop(name, None)

        await agent.teardown()
        self._status[name] = AgentStatus.STOPPED

    async def run_once(self, name: str) -> list[Opportunity]:
        agent = self._agents.get(name)
        if not agent:
            raise KeyError(f"Unknown agent: {name}")
        return await self._execute_scan(agent)

    async def stop_all(self) -> None:
        for name in list(self._tasks):
            await self.stop_agent(name)

    async def _execute_scan(self, agent: Agent) -> list[Opportunity]:
        with tracer.start_as_current_span("agent_scan") as span:
            span.set_attribute("agent.name", agent.name)
            try:
                if self._health_engine:
                    try:
                        from learning.strategy_health import StrategyHealthStatus

                        health_status = await self._health_engine.get_status(agent.name)
                        span.set_attribute("health.status", health_status.value)
                        if health_status in (
                            StrategyHealthStatus.RETIRED,
                            StrategyHealthStatus.SHADOW_ONLY,
                        ):
                            logger.info(
                                "Skipping scan for %s due to health status %s",
                                agent.name,
                                health_status.value,
                            )
                            self._last_run[agent.name] = datetime.now(timezone.utc)
                            if self._emitter:
                                await self._emitter.heartbeat(
                                    agent_name=agent.name,
                                    status=health_status.value,
                                    cycle_count=self._cycle_counts.get(agent.name, 0),
                                )
                            return []
                    except Exception as exc:
                        logger.warning(
                            "Health pre-scan check failed for %s (continuing): %s",
                            agent.name,
                            exc,
                        )
                # --- Memory consultation (consult past lessons/observations before scan) ---
                if self._trade_reflector_factory:
                    try:
                        if agent.name not in self._reflectors:
                            self._reflectors[
                                agent.name
                            ] = await self._trade_reflector_factory(agent.name)
                        reflector = self._reflectors[agent.name]

                        # Query memory for the first few tickers in the universe to get context
                        universe = agent.config.universe
                        if universe:
                            ticker = (
                                universe[0] if isinstance(universe, list) else universe
                            )
                            memories = await reflector.query(
                                symbol=ticker,
                                context="market behavior",
                                agent_name=agent.name,
                            )
                            if memories and self._event_bus:
                                await self._event_bus.publish(
                                    "agent_memory_consultation",
                                    {
                                        "agent_name": agent.name,
                                        "ticker": ticker,
                                        "memories": [
                                            m.get("value", "")[:200] for m in memories
                                        ],
                                    },
                                )
                    except Exception as mem_exc:
                        logger.warning(
                            "Memory consultation failed for %s (continuing): %s",
                            agent.name,
                            mem_exc,
                        )

                # --- Session bias injection (daily market context from trading_rules.yaml) ---
                if self._session_bias_generator:
                    try:
                        bias = await self._session_bias_generator.get_active_bias()
                        if bias:
                            agent._session_bias = bias
                            if self._event_bus:
                                await self._event_bus.publish(
                                    "session_bias_injected",
                                    {
                                        "agent_name": agent.name,
                                        "overall_bias": bias.overall_bias,
                                        "symbol_count": len(bias.symbols),
                                    },
                                )
                    except Exception as bias_exc:
                        logger.warning(
                            "Session bias injection failed for %s (continuing): %s",
                            agent.name,
                            bias_exc,
                        )

                # --- TradingView Chart Context ---
                if hasattr(self, "_tv_fetcher") and self._tv_fetcher:
                    try:
                        universe = agent.config.universe
                        ticker = (
                            universe[0]
                            if isinstance(universe, list) and universe
                            else "UNKNOWN"
                        )
                        tv_context = await self._tv_fetcher.get_latest_chart_context(
                            ticker
                        )
                        if tv_context:
                            agent._tv_context = tv_context
                            if self._event_bus:
                                await self._event_bus.publish(
                                    "tradingview_context_injected",
                                    {
                                        "agent_name": agent.name,
                                        "symbol": ticker,
                                        "drawings": tv_context.get("drawings", []),
                                    },
                                )
                    except Exception as tv_exc:
                        logger.warning(
                            f"TradingView context injection failed for {agent.name}: {tv_exc}"
                        )

                agent.reset_llm_call_count()

                # Check global kill-switch in Redis (Phase A Requirement)
                if self._redis:
                    is_active = await self._redis.get("kill_switch:active")
                    if is_active == b"true" or is_active == "true":
                        logger.warning(
                            f"Scan skipped for {agent.name} - global kill-switch is active"
                        )
                        return

                async with self._scan_semaphore:
                    timeout = (
                        getattr(agent.config, "scan_timeout", None)
                        or self._default_scan_timeout
                    )
                    try:
                        opportunities = await asyncio.wait_for(
                            agent.scan_with_guards(self._data_bus), timeout=timeout
                        )
                    except asyncio.TimeoutError:
                        logger.error(
                            "Agent %s scan timed out after %.1fs", agent.name, timeout
                        )
                        self._error_counts[agent.name] += 1
                        self._last_errors[agent.name] = f"Scan timeout ({timeout}s)"
                        return []
                span.set_attribute("opportunities.found", len(opportunities))

                from models.thought import ActionType

                if not opportunities:
                    universe = getattr(agent, "universe", None) or agent.config.universe
                    ticker = (
                        universe[0]
                        if isinstance(universe, list) and universe
                        else (universe if isinstance(universe, str) else "UNKNOWN")
                    )
                    await self._record_thought(
                        agent_name=agent.name,
                        symbol=ticker,
                        action=ActionType.HOLD,
                        score=0.0,
                        rules=[],
                        memories=[],
                    )
                else:
                    for opp in opportunities:
                        action = (
                            ActionType.BUY
                            if str(opp.signal).lower() in ("buy", "long")
                            else ActionType.SELL
                        )
                        await self._record_thought(
                            agent_name=agent.name,
                            symbol=opp.symbol.ticker,
                            action=action,
                            score=float(opp.confidence),
                            rules=[],
                            memories=[],
                        )

                self._last_run[agent.name] = datetime.now(timezone.utc)
                self._cycle_counts[agent.name] = (
                    self._cycle_counts.get(agent.name, 0) + 1
                )
                if self._emitter:
                    await self._emitter.heartbeat(
                        agent_name=agent.name,
                        status="running",
                        cycle_count=self._cycle_counts[agent.name],
                    )
                for opp in opportunities:
                    if agent.config.broker and not opp.broker_id:
                        opp.broker_id = agent.config.broker
                    await self._router.route(opp, agent.action_level)

                if self._event_bus:
                    await self._event_bus.publish(
                        "agent_run_complete",
                        {
                            "agent_name": agent.name,
                            "opportunities_found": len(opportunities),
                            "timestamp": self._last_run[agent.name].isoformat(),
                        },
                    )

                return opportunities
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                logger.error("Agent %s scan failed: %s", agent.name, e)
                self._error_counts[agent.name] = (
                    self._error_counts.get(agent.name, 0) + 1
                )
                self._last_errors[agent.name] = str(e)
                self._status[agent.name] = AgentStatus.ERROR
                return []

    async def _run_continuous(self, agent: Agent) -> None:
        interval = getattr(agent.config, "interval", 60)
        if not hasattr(agent, "_drain_event") or not agent._drain_event:
            agent._drain_event = asyncio.Event()
        while not agent._draining:
            await self._execute_scan(agent)
            if agent._draining:
                break
            try:
                await asyncio.wait_for(agent._drain_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _run_cron(self, agent: Agent) -> None:
        from croniter import croniter

        if not hasattr(agent, "_drain_event") or not agent._drain_event:
            agent._drain_event = asyncio.Event()

        cron = croniter(agent.config.cron, datetime.now(timezone.utc))
        while not agent._draining:
            next_run = cron.get_next(datetime)
            delay = (next_run - datetime.now(timezone.utc)).total_seconds()
            if delay > 0:
                try:
                    await asyncio.wait_for(agent._drain_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                except asyncio.CancelledError:
                    break
            if agent._draining:
                break
            await self._execute_scan(agent)

    # ------------------------------------------------------------------
    # Registry polling (dynamic agent lifecycle management)
    # ------------------------------------------------------------------

    async def start_polling(self, interval: int = 60) -> None:
        """Start background polling of agent_registry for hot-/warm-/stop operations."""
        if not self._agent_store:
            logger.warning("start_polling called without agent_store — skipping")
            return
        if self._poll_task is not None:
            return
        self._poll_task = asyncio.create_task(self._poll_registry_loop(interval))
        logger.info("Agent registry polling started (every %ds)", interval)

    async def _poll_registry_loop(self, interval: int) -> None:
        while True:
            try:
                await asyncio.sleep(interval)
                await self._reconcile_registry()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Registry poll failed: %s", e)

    async def _reconcile_registry(self) -> None:
        """Reconcile running agents against the registry.

        - Hot-start:   active in registry, not running → instantiate + start
        - Warm-restart: active in registry, running but config changed → stop + re-register + start
        - Hot-stop:    dormant in registry, still running → stop
        """
        from agents.config import _STRATEGY_REGISTRY, _ensure_strategies_registered
        from agents.models import ActionLevel

        if not self._agent_store:
            return

        try:
            registry_entries = await self._agent_store.list_active()
        except Exception as e:
            logger.error("Failed to list active agents from registry: %s", e)
            return

        registry_names = {entry["name"] for entry in registry_entries}
        running_names = set(self._agents.keys())

        # Hot-stop: remove agents no longer active
        for name in running_names - registry_names:
            logger.info(
                "Registry polling: hot-stopping agent '%s' (no longer active)", name
            )
            try:
                await self.stop_agent(name)
                del self._agents[name]
                self._registry_configs.pop(name, None)
            except Exception as e:
                logger.error("Failed to hot-stop agent '%s': %s", name, e)

        _ensure_strategies_registered()

        for entry in registry_entries:
            name = entry["name"]
            strategy = entry.get("strategy", "")

            # Build a config fingerprint for change detection (excludes volatile fields)
            config_fingerprint = {
                "strategy": strategy,
                "schedule": entry.get("schedule"),
                "interval_or_cron": entry.get("interval_or_cron"),
                "universe": entry.get("universe"),
                "parameters": entry.get("parameters"),
                "trust_level": entry.get("trust_level"),
            }

            if name in running_names:
                # Check for warm-restart
                old_fingerprint = self._registry_configs.get(name)
                if old_fingerprint and old_fingerprint != config_fingerprint:
                    logger.info(
                        "Registry polling: warm-restarting agent '%s' (config changed)",
                        name,
                    )
                    try:
                        await self.stop_agent(name)
                    except Exception as e:
                        logger.error(
                            "Failed to stop agent '%s' for warm-restart: %s", name, e
                        )
                        continue
                    # Fall through to re-instantiate below
                    del self._agents[name]
                else:
                    # Sync shadow_mode from registry without restart
                    agent = self._agents.get(name)
                    if agent:
                        registry_shadow = bool(entry.get("shadow_mode", False))
                        if agent.config.shadow_mode != registry_shadow:
                            agent.config.shadow_mode = registry_shadow
                            logger.info(
                                "Synced shadow_mode=%s for '%s' from registry",
                                registry_shadow,
                                name,
                            )
                    self._registry_configs[name] = config_fingerprint
                    continue

            # Hot-start or warm-restart re-instantiation
            factory = _STRATEGY_REGISTRY.get(strategy)
            if not factory:
                logger.warning(
                    "Registry polling: unknown strategy '%s' for agent '%s'",
                    strategy,
                    name,
                )
                continue

            try:
                from agents.models import AgentConfig

                trust_str = entry.get("trust_level", "monitored").lower()
                _trust_to_action = {
                    "monitored": ActionLevel.NOTIFY,
                    "assisted": ActionLevel.SUGGEST_TRADE,
                    "trusted": ActionLevel.SUGGEST_TRADE,
                    "autonomous": ActionLevel.AUTO_EXECUTE,
                }
                action_level = _trust_to_action.get(trust_str, ActionLevel.NOTIFY)

                interval_or_cron = entry.get("interval_or_cron", 60)
                schedule = entry.get("schedule", "continuous")

                # Cron expression lives in parameters.cron because
                # interval_or_cron is an INTEGER column on Postgres and
                # can't hold a cron string. If absent, we'd fall back to
                # stringifying the int, which croniter rejects — so skip
                # registry-driven start for cron agents without parameters.cron.
                _params = entry.get("parameters") or {}
                _cron_expr = _params.get("cron") if schedule == "cron" else None
                if schedule == "cron" and not _cron_expr:
                    logger.warning(
                        "Registry entry for '%s' has schedule=cron but no parameters.cron; skipping registry-driven start (yaml seed path still works)",
                        name,
                    )
                    continue

                agent_config = AgentConfig(
                    name=name,
                    strategy=strategy,
                    schedule=schedule,
                    interval=interval_or_cron if schedule == "continuous" else 60,
                    cron=_cron_expr if schedule == "cron" else None,
                    action_level=action_level,
                    universe=entry.get("universe", []),
                    parameters=entry.get("parameters", {}),
                    shadow_mode=bool(entry.get("shadow_mode", False)),
                    runtime_overrides=entry.get("runtime_overrides", {}),
                )

                agent = factory(agent_config)
                if agent is None:
                    continue
                self.register(agent)
                self._registry_configs[name] = config_fingerprint

                if schedule in ("continuous", "cron"):
                    await self.start_agent(name)
                    logger.info(
                        "Registry polling: started agent '%s' (strategy=%s)",
                        name,
                        strategy,
                    )
            except Exception as e:
                logger.error(
                    "Failed to instantiate agent '%s' from registry: %s", name, e
                )
