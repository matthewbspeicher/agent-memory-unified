from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field as PydanticField

from broker.models import OrderBase, Symbol


class ActionLevel(str, Enum):
    NOTIFY = "notify"
    SUGGEST_TRADE = "suggest_trade"
    AUTO_EXECUTE = "auto_execute"


class AgentStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class OpportunityStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"


class TrustLevel(str, Enum):
    MONITORED = "monitored"
    ASSISTED = "assisted"
    AUTONOMOUS = "autonomous"


class AgentSignal(BaseModel):
    source_agent: str
    target_agent: str | None = None
    signal_type: str
    payload: dict = PydanticField(default_factory=dict)
    expires_at: datetime
    timestamp: datetime = PydanticField(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    confidence: float | None = None  # 0.0 to 1.0, optional


@dataclass
class AgentConfig:
    name: str
    strategy: str
    schedule: str  # "continuous" | "cron" | "on_demand"
    action_level: ActionLevel
    interval: int = 60
    cron: str | None = None
    universe: list[str] | str = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    system_prompt: str | None = None
    tools: list[str] = field(default_factory=list)
    runtime_overrides: dict[str, Any] = field(default_factory=dict)
    trust_level: TrustLevel = TrustLevel.MONITORED
    parameter_bounds: dict[str, dict[str, float]] = field(default_factory=dict)
    optimization: dict[str, dict[str, float]] = field(default_factory=dict)
    remembr_api_token: str | None = None
    exit_rules: list[dict[str, Any]] = field(default_factory=list)
    shadow_mode: bool = False
    promotion_criteria: dict[str, Any] | None = None
    broker: str | None = None  # preferred broker for this agent's opportunities
    regime_policy_mode: str = (
        "annotate_only"  # off | annotate_only | static_gate | empirical_gate
    )
    allowed_regimes: dict[str, list[str]] = field(default_factory=dict)
    disallowed_regimes: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Opportunity:
    id: str
    agent_name: str
    symbol: Symbol
    signal: str
    confidence: float
    reasoning: str
    data: dict[str, Any]
    timestamp: datetime
    status: OpportunityStatus = OpportunityStatus.PENDING
    suggested_trade: OrderBase | None = None
    expires_at: datetime | None = None
    broker_id: str | None = None  # "ibkr" | "kalshi" | "polymarket" | None (→ primary)
    is_exit: bool = False  # True → skip SizingEngine, use full position quantity
    _exit_fraction: float = 1.0  # set by router when PartialExitRule triggers


@dataclass
class AgentInfo:
    name: str
    description: str
    status: AgentStatus
    config: AgentConfig
    last_run: datetime | None = None
    error_count: int = 0
    last_error: str | None = None
