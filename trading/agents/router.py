# agents/router.py
from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from agents.models import ActionLevel, Opportunity, OpportunityStatus
from broker.models import OrderSide

if TYPE_CHECKING:
    from broker.interfaces import Broker
    from data.bus import DataBus
    from data.events import EventBus
    from notifications.base import Notifier
    from risk.engine import RiskEngine
    from storage.opportunities import OpportunityStore
    from storage.trades import TradeStore
    from experiments.ab_test import ExperimentManager
    from tracking.trade_tracker import TradeTracker
    from sizing.engine import SizingEngine
    from exits.manager import ExitManager
    from execution.tracker import ExecutionTracker
    from execution.feedback import SlippageFeedbackLoop
    from regime.agent_filter import RegimeFilter
    from learning.trade_reflector import TradeReflector
    from agents.runner import AgentRunner
    from learning.strategy_health import StrategyHealthEngine
    from learning.signal_features import SignalFeatureCapture
    from storage.execution_costs import ExecutionCostStore
    from learning.confidence_calibration import (
        CalibrationRecommendation,
        ConfidenceCalibrationConfig,
    )
    from storage.confidence_calibration import ConfidenceCalibrationStore
    from agents.meta import MetaAgent
    from execution.shadow import ShadowExecutor
    from rules.engine import RulesEngine

from execution.shadow import ShadowDecisionStatus


from opentelemetry import trace
from utils.telemetry import get_tracer

logger = logging.getLogger(__name__)

tracer = get_tracer(__name__)


class OpportunityRouter:
    def __init__(
        self,
        store: OpportunityStore,
        notifier: Notifier,
        risk_engine: RiskEngine | None = None,
        broker: Broker | None = None,
        brokers: dict[str, Broker] | None = None,
        broker_routing: dict[str, str] | None = None,
        trade_store: TradeStore | None = None,
        data_bus: DataBus | None = None,
        event_bus: EventBus | None = None,
        experiment_manager: ExperimentManager | None = None,
        trade_tracker: TradeTracker | None = None,
        sizing_engine: SizingEngine | None = None,
        exit_manager: ExitManager | None = None,
        execution_tracker: ExecutionTracker | None = None,
        regime_filter: RegimeFilter | None = None,
        slippage_loop: SlippageFeedbackLoop | None = None,
        trade_reflector: TradeReflector | None = None,
        runner: AgentRunner | None = None,
        health_engine: StrategyHealthEngine | None = None,
        signal_feature_capture: SignalFeatureCapture | None = None,
        execution_cost_store: ExecutionCostStore | None = None,
        confidence_calibration_store: ConfidenceCalibrationStore | None = None,
        confidence_calibration_config: ConfidenceCalibrationConfig | None = None,
        meta_agent: MetaAgent | None = None,
        shadow_executor: ShadowExecutor | None = None,
        journal_manager=None,
        rules_engine: "RulesEngine" | None = None,
    ) -> None:
        self._store = store
        self._notifier = notifier
        self._risk_engine = risk_engine
        self._broker = broker
        self._brokers = brokers or {}
        self._broker_routing = broker_routing or {}
        self._trade_store = trade_store
        self._data_bus = data_bus
        self._event_bus = event_bus
        self._experiment_manager = experiment_manager
        self._trade_tracker = trade_tracker
        self._sizing_engine = sizing_engine
        self._exit_manager = exit_manager
        self._execution_tracker = execution_tracker
        self._regime_filter = regime_filter
        self._slippage_loop = slippage_loop
        self._trade_reflector = trade_reflector
        self._runner = runner
        self._health_engine = health_engine
        self._signal_feature_capture = signal_feature_capture
        self._execution_cost_store = execution_cost_store
        self._confidence_calibration_store = confidence_calibration_store
        self._confidence_calibration_config = confidence_calibration_config
        self._meta_agent = meta_agent
        self._shadow_executor = shadow_executor
        self._journal_manager = journal_manager
        self._rules_engine = rules_engine

    def _is_shadow_mode(self, opportunity: Opportunity) -> bool:
        if not self._runner:
            return False
        agent = self._runner.get_agent(opportunity.agent_name)
        if not agent or not hasattr(agent, "config"):
            return False
        return bool(getattr(agent.config, "shadow_mode", False))

    async def _record_shadow_decision(
        self,
        opportunity: Opportunity,
        *,
        decision_status: "ShadowDecisionStatus",
        risk_snapshot: dict | None = None,
        sizing_snapshot: dict | None = None,
        health_snapshot: dict | None = None,
    ) -> None:
        if self._shadow_executor is None:
            logger.warning(
                "Shadow mode enabled for %s but no shadow executor is configured",
                opportunity.id,
            )
            return

        await self._shadow_executor.record(
            opportunity,
            action_level=ActionLevel.AUTO_EXECUTE,
            decision_status=decision_status,
            risk_snapshot=risk_snapshot,
            sizing_snapshot=sizing_snapshot,
            regime_snapshot=opportunity.data.get("regime"),
            health_snapshot=health_snapshot,
        )

    async def _finalize_pre_order_decision(
        self,
        opportunity: Opportunity,
        *,
        shadow_mode: bool,
        decision_status: "ShadowDecisionStatus",
        risk_snapshot: dict | None = None,
        sizing_snapshot: dict | None = None,
        health_snapshot: dict | None = None,
    ) -> bool:
        if shadow_mode:
            await self._record_shadow_decision(
                opportunity,
                decision_status=decision_status,
                risk_snapshot=risk_snapshot,
                sizing_snapshot=sizing_snapshot,
                health_snapshot=health_snapshot,
            )
            return True

        if decision_status != ShadowDecisionStatus.ALLOWED:
            await self._store.update_status(opportunity.id, OpportunityStatus.REJECTED)
            return True

        return False

    def _resolve_broker(self, opportunity: Opportunity) -> "Broker":
        """Resolve which broker handles this opportunity.

        Resolution order:
        1. opportunity.broker_id (agent-specified)
        2. broker_routing config (asset-type mapping)
        3. Primary broker (fallback)
        """
        resolved_name: str | None = None
        resolved_via: str = "primary_fallback"

        # Step 1: Agent-specified broker_id
        if opportunity.broker_id and opportunity.broker_id in self._brokers:
            resolved_name = opportunity.broker_id
            resolved_via = f"broker_id={opportunity.broker_id}"

        # Step 2: Config-driven routing by asset type
        if resolved_name is None:
            asset_type = opportunity.symbol.asset_type.value
            routed = self._broker_routing.get(asset_type)
            if routed and routed in self._brokers:
                resolved_name = routed
                resolved_via = f"broker_routing[{asset_type}]"

        # Step 3: Primary fallback
        if resolved_name is None:
            broker = self._broker
        else:
            broker = self._brokers.get(resolved_name)

        if broker is None:
            raise RuntimeError(f"No broker available for opportunity {opportunity.id}")

        # Liveness check
        if not broker.connection.is_connected():
            raise RuntimeError(
                f"Broker '{resolved_name or 'primary'}' is registered but not connected"
            )

        logger.info(
            "broker_resolution: opportunity=%s resolved=%s via=%s",
            opportunity.symbol.ticker,
            resolved_name or "primary",
            resolved_via,
        )

        return broker

    async def _stamp_regime(self, opportunity: Opportunity) -> None:
        """Fetch SPY regime and stamp normalized RegimeContext into opportunity.data["regime"].

        Runs before the early-return guards so all action levels (NOTIFY, SUGGEST_TRADE,
        AUTO_EXECUTE) get regime metadata. Fails open on any error.
        """
        if not self._data_bus:
            return
        try:
            from regime.detector import RegimeDetector
            from regime.context import RegimeContextResolver
            from broker.models import Symbol as _Sym, AssetType as _AT

            spy = _Sym(ticker="SPY", asset_type=_AT.STOCK)
            bars = await self._data_bus.get_historical(
                spy, timeframe="1d", period="3mo"
            )
            regime = RegimeDetector().detect(bars)
            ctx = RegimeContextResolver().resolve_from_regime(regime)
            opportunity.data["regime"] = ctx.to_dict()
        except Exception as exc:
            logger.warning(
                "Regime stamping failed for %s (non-fatal): %s", opportunity.id, exc
            )

    def _check_regime_policy(self, opportunity: Opportunity) -> str | None:
        """Check the agent's regime policy against the stamped regime context.

        Returns None if allowed, or a rejection reason string if blocked.
        Only active for static_gate mode; annotate_only and off never block.
        """
        if not self._runner:
            return None

        agent = self._runner.get_agent(opportunity.agent_name)
        if not agent or not hasattr(agent, "config"):
            return None

        cfg = agent.config
        mode = getattr(cfg, "regime_policy_mode", "annotate_only") or "annotate_only"

        if mode in ("off", "annotate_only"):
            return None

        if mode != "static_gate":
            return None  # empirical_gate not yet implemented; treat as annotate_only

        regime_data: dict = opportunity.data.get("regime") or {}
        if not regime_data:
            return None  # no regime stamped, allow

        allowed_regimes: dict = getattr(cfg, "allowed_regimes", {}) or {}
        disallowed_regimes: dict = getattr(cfg, "disallowed_regimes", {}) or {}

        violations: list[str] = []

        # Check disallowed first
        for dimension, bad_values in disallowed_regimes.items():
            actual = regime_data.get(dimension)
            if actual and actual in bad_values:
                violations.append(f"{dimension}={actual} is disallowed")

        # Check allowed constraints
        for dimension, ok_values in allowed_regimes.items():
            actual = regime_data.get(dimension)
            if actual and actual not in ok_values:
                violations.append(f"{dimension}={actual} not in allowed {ok_values}")

        if violations:
            return "regime_gate: " + "; ".join(violations)

        return None

    async def _get_confidence_recommendation(
        self,
        opportunity: Opportunity,
    ) -> "CalibrationRecommendation | None":
        if (
            self._confidence_calibration_store is None
            or self._confidence_calibration_config is None
            or not self._confidence_calibration_config.enabled
            or getattr(opportunity, "is_exit", False)
        ):
            return None

        try:
            from learning.confidence_calibration import (
                assign_bucket,
                build_recommendation,
            )

            bucket = assign_bucket(
                opportunity.confidence,
                self._confidence_calibration_config.bucket_width,
            )
            cal_row = await self._confidence_calibration_store.get(
                opportunity.agent_name,
                bucket,
                "all",
            )
            recommendation = build_recommendation(
                bucket=bucket,
                trade_count=int(cal_row["trade_count"]) if cal_row else 0,
                expectancy=(
                    float(cal_row["avg_net_return_pct"])
                    if cal_row and cal_row.get("avg_net_return_pct") is not None
                    else None
                ),
                avg_net_pnl=(
                    float(cal_row["avg_net_pnl"])
                    if cal_row and cal_row.get("avg_net_pnl") is not None
                    else None
                ),
                cfg=self._confidence_calibration_config,
            )
            opportunity.data["confidence_calibration"] = {
                "bucket": recommendation.bucket,
                "sample_quality": recommendation.sample_quality,
                "trade_count": recommendation.trade_count,
                "expectancy": recommendation.expectancy,
                "multiplier": recommendation.multiplier,
                "would_reject": recommendation.would_reject,
                "reason": recommendation.reason,
                "calibrated_score": recommendation.calibrated_score,
                "window": "all",
            }
            if hasattr(self._store, "update_data"):
                try:
                    await self._store.update_data(str(opportunity.id), opportunity.data)
                except Exception as exc:
                    logger.warning(
                        "Failed to persist confidence calibration metadata for %s: %s",
                        opportunity.id,
                        exc,
                    )
            return recommendation
        except Exception as exc:
            logger.warning(
                "Confidence calibration lookup failed for %s: %s",
                opportunity.id,
                exc,
            )
            return None

    async def route(self, opportunity: Opportunity, action_level: ActionLevel) -> None:
        with tracer.start_as_current_span("route_opportunity") as span:
            span.set_attribute("opportunity.id", str(opportunity.id))
            span.set_attribute("opportunity.symbol", opportunity.symbol.ticker)
            span.set_attribute("action_level", action_level.value)

            # --- Regime stamping (before early returns so all action levels get metadata) ---
            try:
                await self._stamp_regime(opportunity)
            except Exception as _stamp_exc:
                logger.warning(
                    "Regime stamp raised unexpectedly for %s: %s",
                    opportunity.id,
                    _stamp_exc,
                )

            # --- External signal annotation ---
            if self._meta_agent:
                try:
                    ext_signals = self._meta_agent.get_signals_for_ticker(
                        opportunity.symbol.ticker
                    )
                    if ext_signals:
                        opportunity.data.setdefault("external_signals", []).extend(
                            [
                                {
                                    "type": s.signal_type,
                                    "source": s.source_agent,
                                    "payload": s.payload,
                                    "timestamp": s.timestamp.isoformat(),
                                }
                                for s in ext_signals
                            ]
                        )
                except Exception as _sig_exc:
                    logger.warning(
                        "Signal annotation failed for %s: %s", opportunity.id, _sig_exc
                    )

            # --- Index-Guided Strategy Retrieval ---
            if self._trade_reflector:
                try:
                    regime_ctx = opportunity.data.get("regime")
                    regime_name = regime_ctx.name if regime_ctx else "unknown"
                    trend = (
                        regime_ctx.trend.value
                        if regime_ctx and hasattr(regime_ctx, "trend")
                        else "unknown"
                    )

                    context_summary = (
                        f"Symbol: {opportunity.symbol.ticker}\n"
                        f"Signal Direction: {opportunity.signal}\n"
                        f"Market Regime: {regime_name}, Trend: {trend}"
                    )

                    strategies = await self._trade_reflector.query_strategies(
                        context_summary
                    )
                    if strategies:
                        opportunity.data["strategies"] = [
                            s.get("value", "") for s in strategies
                        ]
                except Exception as _strat_exc:
                    logger.warning(
                        "Strategy retrieval failed for %s: %s",
                        opportunity.id,
                        _strat_exc,
                    )

            # --- Deja Vu (Memory) annotation ---
            if self._trade_reflector:
                try:
                    memories = await self._trade_reflector.query(
                        symbol=opportunity.symbol.ticker,
                        context=f"{opportunity.signal} signal behavior",
                        agent_name=opportunity.agent_name,
                        top_k=3,
                    )
                    if memories:
                        opportunity.data["deja_vu_memories"] = [
                            m.get("value", "")[:300] for m in memories
                        ]
                        # Check for specific "failure" patterns in recent memory
                        if any(
                            "I would do differently" in m.get("value", "")
                            for m in memories
                        ):
                            opportunity.data.setdefault("external_signals", []).append(
                                {
                                    "type": "memory_warning",
                                    "source": "remembr.dev",
                                    "payload": {
                                        "reason": "Significant past failures detected for this pattern"
                                    },
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }
                            )
                except Exception as _mem_exc:
                    logger.warning(
                        "Deja Vu memory lookup failed for %s: %s",
                        opportunity.id,
                        _mem_exc,
                    )

            await self._store.save(opportunity)

            # --- Signal-time feature capture (best-effort, non-blocking) ---
            if self._signal_feature_capture is not None:
                asyncio.create_task(
                    self._signal_feature_capture.capture(opportunity, action_level)
                )

            if self._data_bus:
                try:
                    import dataclasses

                    quote = await self._data_bus.get_quote(opportunity.symbol)
                    snapshot = {
                        "quote": dataclasses.asdict(quote) if quote else None,
                    }
                    await self._store.save_snapshot(str(opportunity.id), snapshot)
                except Exception as e:
                    logger.warning(
                        "Failed to save snapshot for %s: %s", opportunity.id, e
                    )

            if (
                self._experiment_manager
                and not self._experiment_manager.should_allow_execution(
                    opportunity.agent_name, opportunity.symbol.ticker
                )
            ):
                span.set_attribute("experiment.shadow", True)
                return

            # --- Static regime gating (applies to all action levels when mode=static_gate) ---
            rejection_reason = self._check_regime_policy(opportunity)
            if rejection_reason:
                logger.info(
                    "Regime policy blocked %s (%s): %s",
                    opportunity.agent_name,
                    opportunity.symbol.ticker,
                    rejection_reason,
                )
                if action_level == ActionLevel.AUTO_EXECUTE and self._is_shadow_mode(
                    opportunity
                ):
                    await self._record_shadow_decision(
                        opportunity,
                        decision_status=ShadowDecisionStatus.BLOCKED_REGIME,
                        risk_snapshot={"reason": rejection_reason},
                    )
                    return
                await self._store.update_status(
                    opportunity.id, OpportunityStatus.REJECTED
                )
                return

            await self._notifier.send(opportunity)

            if self._event_bus:
                try:
                    await self._event_bus.publish(
                        "opportunity",
                        {
                            "id": str(opportunity.id),
                            "agent_name": opportunity.agent_name,
                            "symbol": opportunity.symbol.ticker,
                            "signal": opportunity.signal,
                            "confidence": opportunity.confidence,
                        },
                    )
                except Exception:
                    pass  # EventBus publish is best-effort

            if action_level == ActionLevel.NOTIFY:
                return

            if action_level == ActionLevel.SUGGEST_TRADE:
                return  # stored as PENDING, waiting for user approval via API

            if action_level == ActionLevel.AUTO_EXECUTE:
                await self._try_execute(opportunity)

    async def _try_execute(self, opportunity: Opportunity) -> None:
        with tracer.start_as_current_span("try_execute_trade") as span:
            shadow_mode = self._is_shadow_mode(opportunity)
            health_snapshot: dict | None = None
            # --- Strategy health gate (checked before any execution work) ---
            # Health state is separate from AgentStatus (RUNNING/STOPPED/ERROR).
            # Health state takes precedence over tournament stage for execution.
            # See: docs/superpowers/specs/2026-03-31-strategy-throttling-retirement-design.md
            if self._health_engine:
                try:
                    from learning.strategy_health import StrategyHealthStatus

                    health_status = await self._health_engine.get_status(
                        opportunity.agent_name
                    )
                    health_snapshot = {"status": health_status.value}
                    span.set_attribute("health.status", health_status.value)

                    if health_status == StrategyHealthStatus.RETIRED:
                        logger.info(
                            "Execution rejected: agent %s is retired",
                            opportunity.agent_name,
                        )
                        if await self._finalize_pre_order_decision(
                            opportunity,
                            shadow_mode=shadow_mode,
                            decision_status=ShadowDecisionStatus.BLOCKED_HEALTH,
                            health_snapshot=health_snapshot,
                        ):
                            return

                    if health_status == StrategyHealthStatus.SHADOW_ONLY:
                        logger.info(
                            "Shadow-only: storing opportunity for %s but skipping live order",
                            opportunity.agent_name,
                        )
                        if await self._finalize_pre_order_decision(
                            opportunity,
                            shadow_mode=True,
                            decision_status=ShadowDecisionStatus.BLOCKED_HEALTH,
                            health_snapshot=health_snapshot,
                        ):
                            return

                    if health_status == StrategyHealthStatus.WATCHLIST:
                        logger.warning(
                            "Agent %s is on watchlist — executing with full size but monitoring closely",
                            opportunity.agent_name,
                        )
                        # watchlist: execute normally, warning already logged above

                    # throttled: continue to execution; multiplier applied after compute_size()
                except Exception as _he:
                    logger.warning(
                        "Health gate check failed for %s (proceeding): %s",
                        opportunity.agent_name,
                        _he,
                    )

            # Resolve broker (multi-broker routing)
            try:
                broker = self._resolve_broker(opportunity)
            except RuntimeError as e:
                logger.warning("Cannot execute: %s", e)
                if await self._finalize_pre_order_decision(
                    opportunity,
                    shadow_mode=shadow_mode,
                    decision_status=ShadowDecisionStatus.BLOCKED_BROKER_UNAVAILABLE,
                    health_snapshot=health_snapshot,
                    risk_snapshot={"reason": str(e)},
                ):
                    return
                return

            if not self._risk_engine:
                logger.warning(
                    "Cannot auto-execute: risk engine not configured (broker_id=%s)",
                    opportunity.broker_id,
                )
                if await self._finalize_pre_order_decision(
                    opportunity,
                    shadow_mode=shadow_mode,
                    decision_status=ShadowDecisionStatus.BLOCKED_PRECONDITION,
                    health_snapshot=health_snapshot,
                    risk_snapshot={"reason": "risk engine not configured"},
                ):
                    return
                return

            if not opportunity.suggested_trade:
                logger.info("No suggested trade for opportunity %s", opportunity.id)
                if await self._finalize_pre_order_decision(
                    opportunity,
                    shadow_mode=shadow_mode,
                    decision_status=ShadowDecisionStatus.BLOCKED_PRECONDITION,
                    health_snapshot=health_snapshot,
                    risk_snapshot={"reason": "missing suggested trade"},
                ):
                    return
                return

            # Fill account_id from broker when not already set
            if not opportunity.suggested_trade.account_id:
                try:
                    accounts = await broker.account.get_accounts()
                    if accounts:
                        opportunity.suggested_trade.account_id = accounts[0].account_id
                    else:
                        logger.warning(
                            "No accounts on broker — rejecting opportunity %s",
                            opportunity.id,
                        )
                        if await self._finalize_pre_order_decision(
                            opportunity,
                            shadow_mode=shadow_mode,
                            decision_status=ShadowDecisionStatus.BLOCKED_ACCOUNT_UNAVAILABLE,
                            health_snapshot=health_snapshot,
                            risk_snapshot={"reason": "no broker accounts available"},
                        ):
                            return
                except Exception as e:
                    logger.warning("Failed to resolve account_id: %s", e)
                    if await self._finalize_pre_order_decision(
                        opportunity,
                        shadow_mode=shadow_mode,
                        decision_status=ShadowDecisionStatus.BLOCKED_ACCOUNT_UNAVAILABLE,
                        health_snapshot=health_snapshot,
                        risk_snapshot={"reason": str(e)},
                    ):
                        return

            # Zero-quantity guard
            try:
                _qty = opportunity.suggested_trade.quantity
                _allow_sizing_placeholder = (
                    _qty == 0
                    and self._sizing_engine is not None
                    and not getattr(opportunity, "is_exit", False)
                )
                if _qty < 0 or (_qty == 0 and not _allow_sizing_placeholder):
                    logger.warning(
                        "Zero or negative quantity — rejecting opportunity %s",
                        opportunity.id,
                    )
                    if await self._finalize_pre_order_decision(
                        opportunity,
                        shadow_mode=shadow_mode,
                        decision_status=ShadowDecisionStatus.BLOCKED_INVALID_QUANTITY,
                        health_snapshot=health_snapshot,
                    ):
                        return
            except TypeError:
                pass  # quantity type not comparable (e.g., in tests with mocks)

            # Build portfolio context for risk evaluation
            quote = None
            try:
                if self._data_bus:
                    quote = await self._data_bus.get_quote(opportunity.symbol)
            except Exception:
                pass

            if not quote:
                logger.warning("Cannot get quote for risk evaluation")
                if await self._finalize_pre_order_decision(
                    opportunity,
                    shadow_mode=shadow_mode,
                    decision_status=ShadowDecisionStatus.BLOCKED_QUOTE_MISSING,
                    health_snapshot=health_snapshot,
                ):
                    return

            from risk.rules import PortfolioContext

            positions = await self._data_bus.get_positions() if self._data_bus else []
            balance = await self._data_bus.get_balances() if self._data_bus else None

            if not balance:
                if await self._finalize_pre_order_decision(
                    opportunity,
                    shadow_mode=shadow_mode,
                    decision_status=ShadowDecisionStatus.BLOCKED_BALANCE_MISSING,
                    health_snapshot=health_snapshot,
                ):
                    return

            confidence_recommendation = await self._get_confidence_recommendation(
                opportunity
            )
            if confidence_recommendation is not None:
                span.set_attribute(
                    "confidence.bucket",
                    confidence_recommendation.bucket,
                )
                span.set_attribute(
                    "confidence.multiplier",
                    confidence_recommendation.multiplier,
                )
                if confidence_recommendation.would_reject:
                    logger.info(
                        "Confidence calibration rejected %s: %s",
                        opportunity.id,
                        confidence_recommendation.reason,
                    )
                    if await self._finalize_pre_order_decision(
                        opportunity,
                        shadow_mode=shadow_mode,
                        decision_status=ShadowDecisionStatus.BLOCKED_CALIBRATION,
                        health_snapshot=health_snapshot,
                        risk_snapshot={
                            "reason": confidence_recommendation.reason,
                            "bucket": confidence_recommendation.bucket,
                        },
                    ):
                        return

            # Position sizing — override quantity if sizing engine is available (before risk eval)
            # Skip sizing for exit opportunities: use the full position quantity as-is.
            original_quantity = (
                opportunity.suggested_trade.quantity
                if opportunity.suggested_trade is not None
                else None
            )
            if (
                self._sizing_engine
                and opportunity.suggested_trade
                and not getattr(opportunity, "is_exit", False)
            ):
                try:
                    from agents.models import TrustLevel
                    from decimal import Decimal as _D

                    bankroll = balance.buying_power or balance.cash or _D("100000")
                    sized_qty = await self._sizing_engine.compute_size(
                        agent_name=opportunity.agent_name,
                        trust_level=TrustLevel.MONITORED,  # safe default
                        price=quote.last or _D("0"),
                        bankroll=bankroll,
                    )
                    if sized_qty > 0:
                        opportunity.suggested_trade.quantity = sized_qty
                except Exception as exc:
                    logger.warning(
                        "Sizing failed for %s, using original quantity: %s",
                        opportunity.id,
                        exc,
                    )

            if (
                opportunity.suggested_trade
                and opportunity.suggested_trade.quantity <= 0
            ):
                if await self._finalize_pre_order_decision(
                    opportunity,
                    shadow_mode=shadow_mode,
                    decision_status=ShadowDecisionStatus.BLOCKED_INVALID_QUANTITY,
                    sizing_snapshot={
                        "original_quantity": str(original_quantity)
                        if original_quantity is not None
                        else None,
                        "final_quantity": str(opportunity.suggested_trade.quantity),
                    },
                    health_snapshot=health_snapshot,
                    risk_snapshot={
                        "reason": "sizing did not produce a positive quantity"
                    },
                ):
                    return

            if (
                confidence_recommendation
                and opportunity.suggested_trade
                and not getattr(opportunity, "is_exit", False)
            ):
                try:
                    from decimal import Decimal as _D, ROUND_DOWN
                    from learning.confidence_calibration import apply_composed_kelly_cap
                    from sizing.engine import TRUST_KELLY
                    from agents.models import TrustLevel

                    _effective_multiplier = confidence_recommendation.multiplier
                    if self._sizing_engine is not None:
                        _effective_multiplier = apply_composed_kelly_cap(
                            float(TRUST_KELLY.get(TrustLevel.MONITORED, _D("0.25"))),
                            confidence_recommendation.multiplier,
                            self._confidence_calibration_config.max_composed_kelly_fraction,
                        )
                    _orig_qty = _D(str(opportunity.suggested_trade.quantity))
                    _scaled_qty = (_orig_qty * _D(str(_effective_multiplier))).quantize(
                        _D("1"), rounding=ROUND_DOWN
                    )
                    if _scaled_qty <= 0 and _effective_multiplier > 0 and _orig_qty > 0:
                        _scaled_qty = _D("1")
                    if _scaled_qty > 0:
                        opportunity.suggested_trade.quantity = _scaled_qty
                        span.set_attribute(
                            "confidence.effective_multiplier", _effective_multiplier
                        )
                        logger.info(
                            "Confidence-calibrated %s quantity: %s → %s (multiplier=%.2f)",
                            opportunity.agent_name,
                            _orig_qty,
                            _scaled_qty,
                            _effective_multiplier,
                        )
                    else:
                        logger.info(
                            "Confidence calibration reduced quantity to 0 for %s — rejecting",
                            opportunity.agent_name,
                        )
                        if await self._finalize_pre_order_decision(
                            opportunity,
                            shadow_mode=shadow_mode,
                            decision_status=ShadowDecisionStatus.BLOCKED_CALIBRATION,
                            health_snapshot=health_snapshot,
                            risk_snapshot={
                                "reason": "confidence calibration reduced quantity to zero",
                                "bucket": confidence_recommendation.bucket,
                            },
                        ):
                            return
                except Exception as exc:
                    logger.warning(
                        "Confidence calibration sizing failed for %s: %s",
                        opportunity.id,
                        exc,
                    )

            # Apply throttle multiplier AFTER compute_size() — health engine is the
            # single authority for sizing when an agent is throttled (not SizingEngine).
            if (
                self._health_engine
                and opportunity.suggested_trade
                and not getattr(opportunity, "is_exit", False)
            ):
                try:
                    from learning.strategy_health import StrategyHealthStatus

                    _hs = await self._health_engine.get_status(opportunity.agent_name)
                    if _hs == StrategyHealthStatus.THROTTLED:
                        _multiplier = await self._health_engine.get_throttle_multiplier(
                            opportunity.agent_name
                        )
                        from decimal import Decimal as _D

                        _orig_qty = opportunity.suggested_trade.quantity
                        _throttled_qty = int(_D(str(_orig_qty)) * _D(str(_multiplier)))
                        if _throttled_qty > 0:
                            opportunity.suggested_trade.quantity = _throttled_qty
                            span.set_attribute(
                                "health.throttle_multiplier", _multiplier
                            )
                            logger.info(
                                "Throttled %s quantity: %s → %s (multiplier=%.2f)",
                                opportunity.agent_name,
                                _orig_qty,
                                _throttled_qty,
                                _multiplier,
                            )
                        else:
                            logger.info(
                                "Throttle reduced quantity to 0 for %s — rejecting",
                                opportunity.agent_name,
                            )
                            if await self._finalize_pre_order_decision(
                                opportunity,
                                shadow_mode=shadow_mode,
                                decision_status=ShadowDecisionStatus.BLOCKED_HEALTH,
                                health_snapshot={"status": _hs.value},
                                sizing_snapshot={
                                    "original_quantity": str(_orig_qty),
                                    "final_quantity": "0",
                                },
                                risk_snapshot={
                                    "reason": "throttle reduced quantity to zero"
                                },
                            ):
                                return
                except Exception as _te:
                    logger.warning(
                        "Throttle multiplier application failed for %s: %s",
                        opportunity.id,
                        _te,
                    )

            # Partial exit: override quantity based on exit_fraction when set
            _exit_fraction = getattr(opportunity, "_exit_fraction", 1.0)
            if _exit_fraction < 1.0 and opportunity.suggested_trade:
                try:
                    _positions = await broker.account.get_positions(
                        opportunity.suggested_trade.account_id
                    )
                    _pos = next(
                        (p for p in _positions if p.symbol == opportunity.symbol), None
                    )
                    if _pos and _pos.quantity > 0:
                        from decimal import Decimal as _D

                        opportunity.suggested_trade.quantity = (
                            _pos.quantity * _D(str(_exit_fraction))
                        ).quantize(_D("1"))
                except Exception as _pex:
                    logger.warning("Partial exit quantity override failed: %s", _pex)

            ctx = PortfolioContext(positions=positions, balance=balance)
            result = await self._risk_engine.evaluate(
                opportunity.suggested_trade, quote, ctx
            )
            sizing_snapshot = None
            if opportunity.suggested_trade is not None:
                sizing_snapshot = {
                    "original_quantity": str(original_quantity)
                    if original_quantity is not None
                    else None,
                    "final_quantity": str(opportunity.suggested_trade.quantity),
                }
            risk_snapshot = {
                "passed": bool(result.passed),
                "reason": result.reason,
                "adjusted_quantity": (
                    str(result.adjusted_quantity)
                    if result.adjusted_quantity is not None
                    else None
                ),
            }

            if not result.passed:
                logger.info(
                    "Risk blocked trade for %s: %s", opportunity.id, result.reason
                )
                if await self._finalize_pre_order_decision(
                    opportunity,
                    shadow_mode=shadow_mode,
                    decision_status=ShadowDecisionStatus.BLOCKED_RISK,
                    risk_snapshot=risk_snapshot,
                    sizing_snapshot=sizing_snapshot,
                    health_snapshot=health_snapshot,
                ):
                    return

            # Apply dynamic sizing from Governor/RiskEngine
            if result.adjusted_quantity is not None:
                old_qty = opportunity.suggested_trade.quantity
                opportunity.suggested_trade.quantity = result.adjusted_quantity
                logger.info(
                    "RiskEngine adjusted quantity for %s: %s -> %s",
                    opportunity.id,
                    old_qty,
                    result.adjusted_quantity,
                )
                if result.adjusted_quantity <= 0:
                    if await self._finalize_pre_order_decision(
                        opportunity,
                        shadow_mode=shadow_mode,
                        decision_status=ShadowDecisionStatus.BLOCKED_INVALID_QUANTITY,
                        risk_snapshot=risk_snapshot,
                        sizing_snapshot={
                            "original_quantity": str(old_qty),
                            "final_quantity": str(result.adjusted_quantity),
                        },
                        health_snapshot=health_snapshot,
                    ):
                        return

            if shadow_mode:
                if (
                    opportunity.suggested_trade is not None
                    and sizing_snapshot is not None
                ):
                    sizing_snapshot["final_quantity"] = str(
                        opportunity.suggested_trade.quantity
                    )
                risk_snapshot["adjusted_quantity"] = (
                    str(result.adjusted_quantity)
                    if result.adjusted_quantity is not None
                    else None
                )
                if await self._finalize_pre_order_decision(
                    opportunity,
                    shadow_mode=True,
                    decision_status=ShadowDecisionStatus.ALLOWED,
                    risk_snapshot=risk_snapshot,
                    sizing_snapshot=sizing_snapshot,
                    health_snapshot=health_snapshot,
                ):
                    return

            try:
                # Log to Journal Manager
                if self._journal_manager:
                    from journal.models import TradeDecisionSnapshot, TradeExecutionLog

                    # We create a pseudo order_id for the log. When place_order completes,
                    # we could update it, but logging intent before execution is safer for autopsies
                    # if the execution crashes.
                    decision = TradeDecisionSnapshot(
                        agent_id=opportunity.agent_name,
                        symbol=opportunity.symbol.ticker,
                        side=opportunity.suggested_trade.side.value,
                        quantity=float(opportunity.suggested_trade.quantity),
                        signal_type=opportunity.signal,
                        confidence=opportunity.confidence,
                        reasoning=opportunity.reasoning or "",
                        meta_signals=[],
                        governor_limit=None,
                    )
                    execution = TradeExecutionLog(
                        order_id=f"req-{opportunity.id}",
                        broker_id=broker.name if hasattr(broker, "name") else "primary",
                        fill_quantity=0.0,
                        status="pending",
                    )
                    # We don't block execution on logging
                    import asyncio

                    asyncio.create_task(
                        self._journal_manager.log_trade_entry(
                            trade_id=opportunity.id,
                            decision=decision,
                            execution=execution,
                        )
                    )

                order_result = await broker.orders.place_order(
                    opportunity.suggested_trade.account_id,
                    opportunity.suggested_trade,
                )
                await self._store.update_status(
                    opportunity.id, OpportunityStatus.EXECUTED
                )
                if self._trade_store:
                    await self._trade_store.save_trade(
                        opportunity.id,
                        {
                            "order_id": order_result.order_id,
                            "status": order_result.status.value,
                        },
                        {"passed": True},
                    )
                tracked_position_id = None
                if self._trade_tracker:
                    if opportunity.is_exit:
                        tracked_id = opportunity.data.get(
                            "tracked_position_id"
                        ) or opportunity.data.get("position_id")
                        if tracked_id:
                            try:
                                tracked_position_id = int(tracked_id)
                            except (TypeError, ValueError):
                                tracked_position_id = None
                        if tracked_position_id:
                            try:
                                await self._trade_tracker.record_exit(
                                    tracked_position_id,
                                    order_result,
                                    opportunity.data.get("exit_rule", "exit_position"),
                                )
                            except Exception as exc:
                                logger.warning(
                                    "record_exit failed for position %s: %s",
                                    tracked_position_id,
                                    exc,
                                )
                    else:
                        try:
                            side = (
                                "buy"
                                if opportunity.suggested_trade.side == OrderSide.BUY
                                else "sell"
                            )
                            tracked_position_id = (
                                await self._trade_tracker.record_entry(
                                    opportunity,
                                    order_result,
                                    side=side,
                                )
                            )
                        except Exception as exc:
                            logger.warning(
                                "record_entry failed for opportunity %s: %s",
                                opportunity.id,
                                exc,
                            )
                # Record exit lifecycle for tracked positions
                if opportunity.is_exit:
                    if tracked_position_id and self._exit_manager:
                        try:
                            await self._exit_manager.detach(tracked_position_id)
                        except Exception as exc:
                            logger.warning(
                                "exit_manager.detach failed for position %s: %s",
                                tracked_position_id,
                                exc,
                            )
                # Record fill slippage for execution quality tracking
                if self._execution_tracker and order_result:
                    try:
                        from decimal import Decimal as _D

                        actual_price = (
                            _D(str(order_result.avg_fill_price))
                            if hasattr(order_result, "avg_fill_price")
                            and order_result.avg_fill_price
                            else (quote.last or _D("0"))
                        )
                        await self._execution_tracker.record_fill(
                            opportunity_id=str(opportunity.id),
                            agent_name=opportunity.agent_name,
                            broker_id=opportunity.broker_id or "ibkr",
                            expected_price=quote.last or _D("0"),
                            actual_price=actual_price,
                            quantity=opportunity.suggested_trade.quantity,
                            side="BUY"
                            if opportunity.suggested_trade.side == OrderSide.BUY
                            else "SELL",
                            symbol=opportunity.symbol.ticker,
                        )
                    except Exception as exc:
                        logger.warning("Execution tracking failed: %s", exc)
                # Record execution-cost event with full decision-time context
                if self._execution_cost_store and order_result and quote:
                    try:
                        from execution.costs import (
                            decision_price,
                            spread_bps,
                            slippage_bps,
                            order_type_label,
                        )
                        from decimal import Decimal as _D

                        side_str = (
                            "buy"
                            if opportunity.suggested_trade.side == OrderSide.BUY
                            else "sell"
                        )
                        d_price = decision_price(quote.bid, quote.ask, quote.last)
                        fill_p = order_result.avg_fill_price
                        mid = (
                            (quote.bid + quote.ask) / _D("2")
                            if quote.bid is not None and quote.ask is not None
                            else None
                        )

                        await self._execution_cost_store.insert(
                            opportunity_id=str(opportunity.id),
                            tracked_position_id=tracked_position_id,
                            order_id=order_result.order_id or "",
                            agent_name=opportunity.agent_name,
                            symbol=opportunity.symbol.ticker,
                            broker_id=opportunity.broker_id or "ibkr",
                            side=side_str,
                            order_type=order_type_label(opportunity.suggested_trade),
                            decision_time=datetime.now(timezone.utc).isoformat(),
                            decision_bid=str(quote.bid)
                            if quote.bid is not None
                            else None,
                            decision_ask=str(quote.ask)
                            if quote.ask is not None
                            else None,
                            decision_last=str(quote.last)
                            if quote.last is not None
                            else None,
                            decision_price=str(d_price)
                            if d_price is not None
                            else None,
                            fill_time=order_result.filled_at.isoformat()
                            if order_result.filled_at
                            else None,
                            fill_price=str(fill_p) if fill_p is not None else None,
                            filled_quantity=str(order_result.filled_quantity),
                            fees_total=str(order_result.commission),
                            spread_bps=spread_bps(quote.bid, quote.ask, mid),
                            slippage_bps=slippage_bps(fill_p, d_price, side_str)
                            if d_price is not None and fill_p is not None
                            else None,
                            notional=str(fill_p * order_result.filled_quantity)
                            if fill_p is not None
                            else None,
                            status=order_result.status.value
                            if order_result.status
                            else "unknown",
                            fill_source="immediate"
                            if fill_p is not None
                            else "fallback",
                        )
                    except Exception as exc:
                        logger.warning("Execution cost recording failed: %s", exc)
                # Run slippage feedback loop after fill is recorded
                if self._slippage_loop:
                    try:
                        result = await self._slippage_loop.check_agent(
                            opportunity.agent_name
                        )
                        if result:
                            action, new_trust = result
                            logger.info(
                                "SlippageFeedbackLoop %s for %s → %s",
                                action,
                                opportunity.agent_name,
                                new_trust.value,
                            )
                    except Exception as exc:
                        logger.warning("Slippage feedback loop failed: %s", exc)
                # Attach exit rules after successful fill
                if (
                    self._exit_manager
                    and not opportunity.is_exit
                    and tracked_position_id
                ):
                    try:
                        from decimal import Decimal as _D
                        from broker.models import AssetType as _AT
                        from exits.rules import parse_rule as _parse_rule

                        side_str = (
                            "BUY"
                            if opportunity.suggested_trade.side == OrderSide.BUY
                            else "SELL"
                        )
                        asset_type = opportunity.symbol.asset_type

                        # Look up agent config for explicit exit_rules
                        agent_exit_rules_cfg: list[dict] = []
                        if self._runner:
                            _agent_obj = self._runner.get_agent(opportunity.agent_name)
                            if _agent_obj and hasattr(_agent_obj, "config"):
                                agent_exit_rules_cfg = (
                                    _agent_obj.config.exit_rules or []
                                )

                        if agent_exit_rules_cfg:
                            # Agent-declared exit rules (from agents.yaml)
                            exits = [
                                r
                                for r in (_parse_rule(d) for d in agent_exit_rules_cfg)
                                if r is not None
                            ]
                        else:
                            # Default exits: asset-type aware
                            contract_expires_at = None
                            if asset_type == _AT.PREDICTION:
                                try:
                                    details = (
                                        await broker.market_data.get_contract_details(
                                            opportunity.symbol
                                        )
                                    )
                                    contract_expires_at = details.expires_at
                                except Exception as exc:
                                    logger.warning(
                                        "Could not fetch contract details for %s: %s",
                                        opportunity.symbol.ticker,
                                        exc,
                                    )
                            entry_fill_price = (
                                _D(str(order_result.avg_fill_price))
                                if getattr(order_result, "avg_fill_price", None)
                                else (quote.last or _D("0"))
                            )
                            exits = self._exit_manager.compute_default_exits(
                                side=side_str,
                                entry_price=entry_fill_price,
                                asset_type=asset_type,
                                contract_expires_at=contract_expires_at,
                            )

                        await self._exit_manager.attach(
                            position_id=tracked_position_id,
                            rules=exits,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to attach exits for %s: %s", opportunity.id, exc
                        )
                # Kick off post-fill memory hook (lightweight, best-effort)
                if self._trade_reflector and self._trade_tracker:
                    try:
                        from learning.trade_memory import ClosedTrade, TradeMemory
                        from decimal import Decimal as _D
                        import datetime as _dt

                        actual_price = (
                            _D(str(order_result.avg_fill_price))
                            if hasattr(order_result, "avg_fill_price")
                            and order_result.avg_fill_price
                            else (quote.last or _D("0"))
                        )
                        _tm = TradeMemory(
                            symbol=opportunity.symbol.ticker,
                            direction="long"
                            if opportunity.suggested_trade.side == OrderSide.BUY
                            else "short",
                            entry_price=quote.last or _D("0"),
                            exit_price=quote.last
                            or _D("0"),  # entry fill — exit will update
                            pnl=_D("0"),
                            slippage_bps=int(
                                abs(
                                    (actual_price - (quote.last or actual_price))
                                    / (quote.last or _D("1"))
                                    * 10000
                                )
                            )
                            if self._execution_tracker
                            else 0,
                            signal_strength=opportunity.confidence,
                            outcome="scratch",  # updated when position closes
                            hold_duration_mins=0,
                            timestamp=_dt.datetime.now(_dt.timezone.utc),
                        )
                        _ct = ClosedTrade(
                            agent_name=opportunity.agent_name,
                            opportunity_id=str(opportunity.id),
                            trade_memory=_tm,
                            expected_pnl=_D("0"),
                            stop_loss=_D("-1"),
                        )
                        asyncio.create_task(
                            self._trade_reflector.reflect(_ct, opportunity.agent_name)
                        )
                    except Exception as _re:
                        logger.warning("Trade reflection hook failed: %s", _re)
                # Kick off health recompute after trade closes (non-blocking, best-effort)
                # Same pattern as trade_reflector above. Reads PerformanceStore.get_latest()
                # which is maintained by the mark-to-market scheduler.
                if self._health_engine and opportunity.is_exit:
                    asyncio.create_task(
                        self._health_engine.on_trade_closed(opportunity.agent_name)
                    )
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                logger.error("Trade execution failed for %s: %s", opportunity.id, e)
                await self._store.update_status(
                    opportunity.id, OpportunityStatus.REJECTED
                )


class ConsensusRouter:
    """
    Wraps an OpportunityRouter to require N-of-M agent agreement before auto-executing.
    If consensus is reached, it elevates the action level to AUTO_EXECUTE.

    When consensus_store is provided, votes are persisted to SQLite and survive restarts.
    When None, falls back to in-memory dict (suitable for tests).
    """

    def __init__(
        self,
        target_router: OpportunityRouter,
        threshold: int = 2,
        window_minutes: int = 15,
        consensus_store=None,
    ) -> None:
        self._target = target_router
        self._threshold = threshold
        self._window = timedelta(minutes=window_minutes)
        self._store = consensus_store
        # In-memory fallback: (ticker, side) -> {agent_name: Opportunity}
        self._pending: dict[tuple[str, OrderSide], dict[str, Opportunity]] = (
            defaultdict(dict)
        )

    async def route(self, opportunity: Opportunity, action_level: ActionLevel) -> None:
        with tracer.start_as_current_span("consensus_route"):
            if not opportunity.suggested_trade:
                await self._target.route(opportunity, action_level)
                return

            now = opportunity.timestamp
            if not now.tzinfo:
                now = now.replace(tzinfo=timezone.utc)

            side = opportunity.suggested_trade.side
            key = (opportunity.symbol.ticker, side)

            if self._store is not None:
                await self._route_persistent(opportunity, action_level, key, side, now)
            else:
                await self._route_in_memory(opportunity, action_level, key, now)

    async def _route_persistent(
        self,
        opportunity: Opportunity,
        action_level: ActionLevel,
        key: tuple,
        side: OrderSide,
        now: datetime,
    ) -> None:
        cutoff = now - self._window
        await self._store.cleanup_expired(cutoff)
        await self._store.add_vote(
            key[0], side.value, opportunity.agent_name, str(opportunity.id), now
        )
        votes = await self._store.get_votes(key[0], side.value, cutoff)

        if len(votes) >= self._threshold:
            await self._store.clear_votes(key[0], side.value)
            logger.info(
                "Consensus reached for %s side %s among %d agents",
                key[0],
                side.value,
                len(votes),
            )
            opportunity.reasoning += f" [Consensus reached among {len(votes)} agents]"
            if getattr(self._target, "_event_bus", None):
                await self._target._event_bus.publish(
                    "consensus", {"symbol": key[0], "side": side.value}
                )
            await self._target.route(opportunity, ActionLevel.AUTO_EXECUTE)
        else:
            await self._target.route(opportunity, action_level)

    async def _route_in_memory(
        self,
        opportunity: Opportunity,
        action_level: ActionLevel,
        key: tuple,
        now: datetime,
    ) -> None:
        self._pending[key][opportunity.agent_name] = opportunity

        valid_agents = {
            name: opp
            for name, opp in self._pending[key].items()
            if (
                now
                - (
                    opp.timestamp
                    if opp.timestamp.tzinfo
                    else opp.timestamp.replace(tzinfo=timezone.utc)
                )
            )
            <= self._window
        }
        self._pending[key] = valid_agents

        if len(valid_agents) >= self._threshold:
            self._pending[key].clear()
            logger.info(
                "Consensus reached for %s side %s among %d agents",
                key[0],
                opportunity.suggested_trade.side.value,
                len(valid_agents),
            )
            opportunity.reasoning += (
                f" [Consensus reached among {len(valid_agents)} agents]"
            )
            if getattr(self._target, "_event_bus", None):
                await self._target._event_bus.publish(
                    "consensus",
                    {"symbol": key[0], "side": opportunity.suggested_trade.side.value},
                )
            await self._target.route(opportunity, ActionLevel.AUTO_EXECUTE)
        else:
            await self._target.route(opportunity, action_level)
