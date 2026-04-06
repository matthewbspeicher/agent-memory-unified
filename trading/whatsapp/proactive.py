import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING
from agents.models import AgentStatus

if TYPE_CHECKING:
    from whatsapp.assistant import WhatsAppAssistant

logger = logging.getLogger(__name__)

from opentelemetry import metrics

meter = metrics.get_meter("hermes.proactive")
tuning_cycles_counter = meter.create_counter(
    "hermes.tuning_cycles_total",
    description="Total number of tuning and exploration cycles",
)
agents_spawned_counter = meter.create_counter(
    "hermes.agents_spawned_total",
    description="Total number of shadow agents spawned via Hermes",
)


class HermesProactiveOps:
    """
    Background worker that runs proactive monitoring and intelligence-gathering
    skills for the Hermes agent. Handles health monitors, daily briefs,
    and automated tuning autopsies.
    """

    def __init__(
        self, assistant: "WhatsAppAssistant", allowed_numbers: list[str]
    ) -> None:
        self.wa = assistant
        self.allowed_numbers = allowed_numbers
        self._running = False
        self._last_brief_date = ""

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        asyncio.create_task(self._health_monitor_loop())
        asyncio.create_task(self._daily_briefing_loop())
        asyncio.create_task(self._tuning_and_autopsy_loop())
        asyncio.create_task(self._parameter_exploration_loop())
        asyncio.create_task(self._shadow_evaluation_loop())
        logger.info("Hermes proactive operations started")

    def stop(self) -> None:
        self._running = False

    async def _broadcast(self, text: str) -> None:
        """Helper to send a message to all allowed administrative WhatsApp numbers."""
        for number in self.allowed_numbers:
            try:
                await self.wa._client.send_text(number, text)
            except Exception as e:
                logger.error(f"Failed to send proactive message to {number}: {e}")

    async def _health_monitor_loop(self) -> None:
        """
        Periodically checks connectivity and checks for container exceptions.
        """
        while self._running:
            try:
                # Runs every 5 minutes
                await asyncio.sleep(300)

                is_healthy = False
                try:
                    if self.wa._broker:
                        is_healthy = self.wa._broker.connection.is_connected()
                        if hasattr(self.wa._broker, "check_health"):
                            # Pings predicting markets for active connection checks
                            is_healthy = (
                                is_healthy and await self.wa._broker.check_health()
                            )
                    else:
                        is_healthy = True  # Paper mode with no broker setup defaults to healthy logic
                except Exception as e:
                    logger.warning("Proactive health check encountered an error: %s", e)
                    is_healthy = False

                if not is_healthy:
                    logger.warning(
                        "Hermes detected platform is unhealthy. Fetching recent container logs..."
                    )

                    # NOTE: This assumes the host is WSL2 or a container with access to the docker sock
                    # and the container name is 'stock-trading-api'.
                    proc = await asyncio.create_subprocess_shell(
                        "docker compose logs stock-trading-api --tail 50",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await proc.communicate()
                    log_output = (stdout.decode() or "") + (stderr.decode() or "")

                    if len(log_output) > 2000:
                        log_output = "...[truncated]...\n" + log_output[-1900:]

                    msg = (
                        "🚨 *Hermes Health Alert* 🚨\n"
                        "Platform heartbeat failed. Recent logs:\n\n"
                        f"```\n{log_output.strip()}\n```"
                    )
                    await self._broadcast(msg)

                    # Backoff for 1 hour after alerting to avoid spam
                    await asyncio.sleep(3600)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Hermes health monitor loop error: %s", e)

    async def _daily_briefing_loop(self) -> None:
        """
        Sends the morning brief once per day at 08:30 server time.
        """
        while self._running:
            try:
                now = datetime.now()
                current_date = now.strftime("%Y-%m-%d")

                # Check if it is currently 08:30 and the brief hasn't been sent today
                if (
                    now.hour == 8
                    and now.minute == 30
                    and self._last_brief_date != current_date
                ):
                    logger.info("Hermes generating proactive morning brief...")
                    if self.wa._brief_generator:
                        data = await self.wa._brief_generator.get_or_generate()
                        msg = f"🌅 *Morning Brief* ({data['date']}):\n\n{data['brief']}"
                        await self._broadcast(msg)
                        self._last_brief_date = current_date
                    else:
                        logger.warning(
                            "Brief generator missing in proactive morning brief loop."
                        )

                # Check clock every minute
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Hermes daily briefing loop error: %s", e)

    async def _tuning_and_autopsy_loop(self) -> None:
        """
        Runs every 4 hours to evaluate agent Sharpes for automated tuning
        and runs silent autopsies on newly closed positions.
        """
        # local imports to avoid circular dependencies during boot
        from agents.tuning import AdaptiveTuner
        from storage.performance import PerformanceStore
        from storage.opportunities import OpportunityStore
        from storage.trades import TradeStore

        while self._running:
            try:
                # Wait 4 hours (14400 seconds) prior to execution (or sleep immediately and run later)
                # We'll run early, then sleep to allow startup to finish, but for robust design we sleep first
                await asyncio.sleep(14400)

                if not self.wa._db:
                    continue

                trade_store = TradeStore(self.wa._db)
                perf_store = PerformanceStore(self.wa._db)

                # 1. Tuning Logic
                logger.info(
                    "Hermes scanning agents for automated performance tuning..."
                )
                agents = self.wa._runner.list_agents()
                for info in agents:
                    if info.status != AgentStatus.RUNNING:
                        continue
                    agent_name = info.name

                    # Extract last known performance from the db
                    history = await perf_store.get_history(agent_name, limit=1)
                    if history:
                        latest = history[0]
                        # Trigger tuning if 30-day trailing sharpe is dangerously low (e.g. < 0.5)
                        if latest.sharpe_ratio < 0.5 and latest.position_count > 5:
                            logger.info(
                                f"Agent {agent_name} trailing Sharpe {latest.sharpe_ratio} < 0.5. Triggering autotune."
                            )
                            try:
                                opp_store = OpportunityStore(self.wa._db)
                                tuner = AdaptiveTuner(
                                    self.wa._runner, opp_store, trade_store
                                )
                                await tuner.tune_agent(agent_name)
                                msg = f"🔧 *Hermes Auto-Tuner*\nAutomatically tuned `{agent_name}` due to deteriorating Sharpe ({latest.sharpe_ratio:.2f})."
                                await self._broadcast(msg)
                            except Exception as e:
                                logger.error(f"Failed to autotune {agent_name}: {e}")

                # 2. Autopsy Logic
                logger.info("Hermes scanning for recent trades needing autopsy...")
                if self.wa._journal_service:
                    # Get the most recent 5 closed trades missing autopsy analysis
                    # We can list through JournalService to see what is missing autopsy
                    entries = await self.wa._journal_service.list_trades(limit=10)
                    for entry in entries:
                        if not entry.has_autopsy:
                            logger.info(
                                f"Hermes running autonomous autopsy on trade {entry.position_id}..."
                            )
                            try:
                                # This generates and caches the autopsy automatically via LLM
                                await self.wa._journal_service.get_trade_detail(
                                    entry.position_id
                                )
                            except Exception as e:
                                logger.warning(
                                    f"autonomous autopsy failed for {entry.position_id}: {e}"
                                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Hermes tuning and autopsy loop error: %s", e)

    async def _parameter_exploration_loop(self) -> None:
        """Every 8 hours, explore parameter variations for underperforming agents.

        For each agent with trailing Sharpe < 1.0:
        1. Generate 3 parameter variants via LLM suggestions (AdaptiveTuner)
        2. Run each through BacktestSandbox
        3. If any variant beats the current config's Sharpe by >0.2, notify
        4. Requests interactive WhatsApp APPROVE before spawning the shadow variant
        """
        from backtesting.sandbox import BacktestSandbox
        from storage.performance import PerformanceStore
        from storage.opportunities import OpportunityStore
        from storage.trades import TradeStore
        from agents.tuning import AdaptiveTuner

        while self._running:
            try:
                await asyncio.sleep(28800)  # 8 hours

                if not self.wa._db or not self.wa._data_bus:
                    continue

                perf_store = PerformanceStore(self.wa._db)
                opp_store = OpportunityStore(self.wa._db)
                trade_store = TradeStore(self.wa._db)
                tuner = AdaptiveTuner(self.wa._runner, opp_store, trade_store)
                sandbox = BacktestSandbox(data_bus=self.wa._data_bus)
                agents = self.wa._runner.list_agents()

                tuning_cycles_counter.add(1)

                for info in agents:
                    try:
                        if info.status.value != "RUNNING":
                            continue

                        # Check trailing performance
                        history = await perf_store.get_history(info.name, limit=1)
                        if not history:
                            continue

                        latest = history[0]
                        if latest.sharpe_ratio >= 1.0:
                            continue  # performing well, skip

                        config = info.config
                        if not config or not config.parameters:
                            continue

                        strategy = config.strategy
                        base_params = config.parameters.copy()
                        universe = config.universe
                        symbols = (
                            universe
                            if isinstance(universe, list)
                            else [universe]
                            if isinstance(universe, str)
                            else ["AAPL", "MSFT", "GOOGL"]
                        )

                        # Generate parameter variants via LLM
                        snapshot = {
                            "sharpe_ratio": latest.sharpe_ratio,
                            "win_rate": latest.win_rate,
                            "total_trades": latest.total_trades,
                        }
                        variants = await tuner.generate_parameter_variants(
                            info.name, strategy, base_params, snapshot
                        )
                        if not variants:
                            continue

                        logger.info(
                            "Hermes exploring %d LLM parameter variants for %s (Sharpe=%.2f)",
                            len(variants),
                            info.name,
                            latest.sharpe_ratio,
                        )

                        # Evaluate all variants
                        results = await sandbox.evaluate_variants(
                            strategy=strategy,
                            base_parameters=base_params,
                            variants=variants,
                            symbols=symbols[:10],  # cap symbols for speed
                            period="6mo",
                        )

                        # Check if any variant beats current by >0.2 Sharpe
                        best = results[0] if results else None
                        if best and best.sharpe_ratio > latest.sharpe_ratio + 0.2:
                            improvement = best.sharpe_ratio - latest.sharpe_ratio

                            gen_suffix = datetime.now().strftime("%m%d%H%M")
                            evolved_name = f"{info.name}_gen{gen_suffix}"

                            msg = (
                                f"🧪 *Hermes LLM Parameter Discovery*\n"
                                f"Agent: `{info.name}` (strategy: {strategy})\n"
                                f"Current Sharpe: {latest.sharpe_ratio:.2f}\n"
                                f"Best variant Sharpe: {best.sharpe_ratio:.2f} (+{improvement:.2f})\n"
                                f"Suggested params: {best.parameters}\n\n"
                                f"Trades: {best.total_trades} | Win rate: {best.win_rate:.1f}% | "
                                f"Max DD: {best.max_drawdown_pct:.1f}%\n\n"
                            )

                            agent_store = getattr(self.wa, "_agent_store", None)
                            if agent_store and improvement > 0.5:
                                spawn_data = {
                                    "name": evolved_name,
                                    "strategy": strategy,
                                    "parent_name": info.name,
                                    "parameters": best.parameters,
                                    "universe": symbols,
                                    "creation_context": {
                                        "reason": "llm_parameter_exploration",
                                        "parent_sharpe": latest.sharpe_ratio,
                                        "variant_sharpe": best.sharpe_ratio,
                                        "improvement": improvement,
                                    },
                                }

                                full_autonomy = getattr(
                                    self.wa._settings, "hermes_full_autonomy", False
                                )
                                if full_autonomy:
                                    logger.info(
                                        "Full Autonomy: auto-spawning shadow agent %s",
                                        evolved_name,
                                    )
                                    await agent_store.create_evolved_agent(**spawn_data)
                                    await self._broadcast(
                                        f"🧬 *Hermes Autonomous Evolution*\n"
                                        f"Auto-spawned shadow variant `{evolved_name}`\n"
                                        f"Improvement: +{improvement:.2f}"
                                    )
                                else:
                                    msg += f"🧬 Evolved shadow agent `{evolved_name}` ready to spawn.\n"
                                    msg += "Reply *APPROVE* to spawn this shadow agent for real-time validation via WhatsApp."

                                    for phone in self.allowed_numbers:
                                        self.wa._confirmation_gate.request(
                                            phone,
                                            action_type="spawn_shadow",
                                            data=spawn_data,
                                        )

                                    agents_spawned_counter.add(1)
                            else:
                                msg += f"To apply: update agent `{info.name}` parameters via API."

                            await self._broadcast(msg)
                            logger.info(
                                "Hermes found improvement for %s: Sharpe %.2f -> %.2f",
                                info.name,
                                latest.sharpe_ratio,
                                best.sharpe_ratio,
                            )
                    except Exception as e:
                        logger.warning(
                            "Parameter exploration failed for %s: %s", info.name, e
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Hermes parameter exploration loop error: %s", e)

    async def _shadow_evaluation_loop(self) -> None:
        """Evaluate shadow agents for promotion or pruning every 24 hours."""
        from storage.shadow import ShadowExecutionStore

        while self._running:
            try:
                await asyncio.sleep(86400)  # 24 hours

                agent_store = getattr(self.wa, "_agent_store", None)
                if not agent_store:
                    continue

                db = getattr(self.wa, "_db", None)
                if not db:
                    continue

                shadow_store = ShadowExecutionStore(db)
                agents = await agent_store.list_all()
                for agent in agents:
                    # Agent registry returns dicts
                    is_shadow = bool(agent.get("shadow_mode", False))
                    status = agent.get("status", "").upper()

                    if not is_shadow or status != "ACTIVE":
                        continue

                    criteria = agent.get("promotion_criteria")
                    if criteria and "min_sharpe" in criteria:
                        agent_name = agent["name"]
                        stats = await shadow_store.summary_for_agent(agent_name)
                        if not stats:
                            continue

                        min_sharpe = criteria["min_sharpe"]
                        min_trades = criteria.get("min_trades", 10)

                        sharpe = stats.get("sharpe_ratio", 0.0)
                        resolved_trades = stats.get("resolved_count", 0)

                        if sharpe >= min_sharpe and resolved_trades >= min_trades:
                            # Auto-promote
                            await agent_store.set_shadow_mode(agent_name, False)

                            # Update running instance if it exists
                            if self.wa._runner:
                                await self.wa._runner.update_agent_shadow_mode(
                                    agent_name, shadow_mode=False
                                )

                            await self._broadcast(
                                f"🚀 *Hermes Auto-Promotion*\n"
                                f"Shadow Agent `{agent_name}` passed promotion criteria!\n"
                                f"Sharpe: {sharpe:.2f} >= {min_sharpe}\n"
                                f"Trades: {resolved_trades} >= {min_trades}\n"
                                f"It is now trading live capital."
                            )
                        elif sharpe < 0.0 and resolved_trades >= min_trades:
                            # Prune
                            await agent_store.set_status(agent_name, "dormant")
                            await self._broadcast(
                                f"🥀 *Hermes Auto-Pruning*\n"
                                f"Shadow Agent `{agent_name}` failed validation (Sharpe {sharpe:.2f}) and has been decommissioned."
                            )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Hermes shadow evaluation loop error: %s", e)
