# agents/config.py
from __future__ import annotations
import json
import logging
from collections.abc import Callable
from typing import Any, Literal
import yaml
from pydantic import BaseModel, Field, field_validator

from agents.base import Agent
from agents.models import ActionLevel, AgentConfig, TrustLevel
from storage.agent_registry import AgentStore

logger = logging.getLogger(__name__)

# Strategy registry — maps strategy names to classes or factory callables
_STRATEGY_REGISTRY: dict[str, type[Agent] | Callable[[AgentConfig], Agent]] = {}


class AgentConfigSchema(BaseModel):
    name: str
    strategy: str
    universe: str | list[str] = Field(default_factory=list)
    interval: int = 60
    schedule: Literal["continuous", "cron", "on_demand"] = "on_demand"
    action_level: str = "notify"
    model: str | None = None
    trust_level: str = "monitored"
    system_prompt: str | None = None
    cron: str | None = None
    parameters: dict = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    remembr_api_token: str | None = None
    exit_rules: list[dict] = Field(default_factory=list)
    shadow_mode: bool = False
    broker: str | None = None
    regime_policy_mode: str | None = None
    allowed_regimes: dict | None = None
    disallowed_regimes: dict | None = None

    @field_validator("regime_policy_mode")
    @classmethod
    def regime_policy_mode_must_be_valid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        valid = {"off", "annotate_only", "static_gate", "empirical_gate"}
        if v not in valid:
            raise ValueError(
                f"Invalid regime_policy_mode '{v}'. Must be one of: {sorted(valid)}"
            )
        return v

    @field_validator("exit_rules")
    @classmethod
    def exit_rules_must_have_valid_types(cls, v: list[dict]) -> list[dict]:
        valid_types = {
            "stop_loss",
            "take_profit",
            "trailing_stop",
            "time_exit",
            "prediction_time_exit",
            "conviction_exit",
            "pre_expiry_exit",
            "probability_trailing_stop",
            "partial_exit",
        }
        for rule in v:
            rule_type = rule.get("type")
            if rule_type not in valid_types:
                raise ValueError(
                    f"Unknown exit rule type '{rule_type}'. Valid: {sorted(valid_types)}"
                )
        return v

    @field_validator("strategy")
    @classmethod
    def strategy_must_be_known(cls, v: str) -> str:
        if _STRATEGY_REGISTRY and v not in _STRATEGY_REGISTRY:
            raise ValueError(
                f"Unknown strategy '{v}'. Known: {sorted(_STRATEGY_REGISTRY)}"
            )
        return v

    @field_validator("action_level")
    @classmethod
    def action_level_must_be_valid(cls, v: str) -> str:
        valid = {al.value for al in ActionLevel}
        if v not in valid:
            raise ValueError(
                f"Invalid action_level '{v}'. Must be one of: {sorted(valid)}"
            )
        return v

    @field_validator("trust_level")
    @classmethod
    def trust_level_must_be_valid(cls, v: str) -> str:
        valid = {tl.value for tl in TrustLevel}
        if v not in valid:
            raise ValueError(
                f"Invalid trust_level '{v}'. Must be one of: {sorted(valid)}"
            )
        return v

    @field_validator("interval")
    @classmethod
    def interval_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"interval must be positive, got {v}")
        return v


class AgentsFileSchema(BaseModel):
    agents: list[AgentConfigSchema] = Field(default_factory=list)


def register_strategy(
    name: str, factory: type[Agent] | Callable[[AgentConfig], Agent]
) -> None:
    _STRATEGY_REGISTRY[name] = factory


def _ensure_strategies_registered() -> None:
    if _STRATEGY_REGISTRY:
        return
    from strategies.rsi import RSIAgent
    from strategies.volume_spike import VolumeSpikeAgent
    from strategies.llm_analyst import LLMAnalystAgent
    from strategies.portfolio import PositionMonitorAgent, TaxLossHarvestingAgent
    from strategies.kalshi_news_arb import KalshiNewsArbAgent
    from strategies.kalshi_time_decay import KalshiTimeDecayAgent
    from strategies.kalshi_calibration import KalshiCalibrationAgent
    from strategies.exit_monitor import ExitMonitorAgent

    register_strategy("rsi", RSIAgent)
    register_strategy("volume_spike", VolumeSpikeAgent)
    register_strategy("llm", LLMAnalystAgent)
    register_strategy("position_monitor", PositionMonitorAgent)
    register_strategy("tax_loss", TaxLossHarvestingAgent)
    register_strategy("kalshi_news_arb", KalshiNewsArbAgent)
    register_strategy("kalshi_time_decay", KalshiTimeDecayAgent)
    register_strategy("kalshi_calibration", KalshiCalibrationAgent)
    register_strategy("exit_monitor", ExitMonitorAgent)
    try:
        from strategies.polymarket_news_arb import PolymarketNewsArbAgent
        from strategies.polymarket_calibration import PolymarketCalibrationAgent
        from strategies.polymarket_time_decay import PolymarketTimeDecayAgent

        register_strategy("polymarket_news_arb", PolymarketNewsArbAgent)
        register_strategy("polymarket_calibration", PolymarketCalibrationAgent)
        register_strategy("polymarket_time_decay", PolymarketTimeDecayAgent)
    except ImportError:
        logger.info(
            "Polymarket strategies unavailable (missing eth_account/py_clob_client)"
        )
    from strategies.bittensor_signal import BittensorSignalAgent

    register_strategy("bittensor_signal", BittensorSignalAgent)
    from strategies.bittensor_consensus import BittensorAlphaAgent

    register_strategy("bittensor_alpha", BittensorAlphaAgent)
    from strategies.momentum import MomentumAgent
    from strategies.mean_reversion import MeanReversionAgent
    from strategies.breakout import BreakoutAgent
    from strategies.multi_factor import MultiFactorAgent
    from strategies.multi_timeframe_consensus import MultiTimeframeConsensusAgent

    register_strategy("momentum", MomentumAgent)
    register_strategy("mean_reversion", MeanReversionAgent)
    register_strategy("breakout", BreakoutAgent)
    register_strategy("multi_factor", MultiFactorAgent)
    register_strategy("multi_timeframe_consensus", MultiTimeframeConsensusAgent)

    from strategies.correlation_monitor import StrategyCorrelationMonitor
    from strategies.ensemble_optimizer import EnsembleOptimizer

    register_strategy("correlation_monitor", StrategyCorrelationMonitor)
    register_strategy("ensemble_optimizer", EnsembleOptimizer)


def load_agents_config(path: str, prompt_store: Any = None) -> list[Agent]:
    _ensure_strategies_registered()
    with open(path) as f:
        data = yaml.safe_load(f)

    from pydantic import ValidationError

    try:
        parsed = AgentsFileSchema(agents=data.get("agents", []))
    except ValidationError as exc:
        raise ValueError(f"Invalid agents config '{path}': {exc.errors()}") from exc

    from agents.base import LLMAgent

    agents: list[Agent] = []
    for entry in parsed.agents:
        strategy = entry.strategy
        factory = _STRATEGY_REGISTRY.get(strategy)
        if factory is None:
            raise ValueError(
                f"Unknown strategy: {strategy}. Known: {list(_STRATEGY_REGISTRY)}"
            )

        config = AgentConfig(
            name=entry.name,
            strategy=strategy,
            schedule=entry.schedule,
            action_level=ActionLevel(entry.action_level),
            interval=entry.interval,
            cron=entry.cron,
            universe=entry.universe,
            parameters=entry.parameters,
            model=entry.model,
            system_prompt=entry.system_prompt,
            tools=entry.tools,
            trust_level=TrustLevel(entry.trust_level),
            remembr_api_token=entry.remembr_api_token,
            exit_rules=entry.exit_rules,
            shadow_mode=entry.shadow_mode,
            broker=entry.broker,
            regime_policy_mode=entry.regime_policy_mode or "annotate_only",
            allowed_regimes=entry.allowed_regimes or {},
            disallowed_regimes=entry.disallowed_regimes or {},
        )
        if isinstance(factory, type) and issubclass(factory, LLMAgent) and prompt_store:
            agents.append(factory(config=config, prompt_store=prompt_store))
        elif isinstance(factory, type):
            agents.append(factory(config=config))
        else:
            # Callable factory (e.g. closure with injected deps)
            agents.append(factory(config))

    return agents


async def apply_overrides(
    config: AgentConfig, store: AgentStore
) -> AgentConfig:
    """
    Merge DB-persisted overrides on top of YAML-loaded config.

    Args:
        config: The base AgentConfig loaded from YAML
        store: The AgentStore (agent_registry) to query for overrides

    Returns:
        Updated AgentConfig with DB overrides applied
    """
    entry = await store.get(config.name)
    if not entry:
        return config

    if entry.get("trust_level"):
        config.trust_level = TrustLevel(entry["trust_level"])

    overrides = entry.get("runtime_overrides", {})
    if overrides:
        config.runtime_overrides = overrides
        if "remembr_api_token" in overrides:
            config.remembr_api_token = overrides["remembr_api_token"]

    return config
