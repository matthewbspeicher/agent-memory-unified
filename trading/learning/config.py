from typing import Any
from pydantic import BaseModel, Field


class PnlConfig(BaseModel):
    mark_to_market_seconds: int = 60
    reconciliation_seconds: int = 300


class RetentionConfig(BaseModel):
    default_days: int = 90
    per_agent: dict[str, int] = Field(default_factory=dict)


class OptimizationConfig(BaseModel):
    min_backtest_trades: int = 30
    min_paper_days: int = 7
    tournament_challengers: int = 4
    tournament_promotion_margin: float = Field(default=0.10, gt=0, lt=1)
    grid_search_schedule: str = "0 2 * * 0"


class ReflectionConfig(BaseModel):
    feedback_model: str = "claude-sonnet-4-20250514"
    synthesis_model: str = "claude-sonnet-4-20250514"
    synthesis_interval_days: int = 7
    max_learned_rules: int = 10
    recent_lessons_window: int = 5
    auto_revert_sharpe_drop: float = Field(default=0.20, ge=0, le=1)


class GuardrailsConfig(BaseModel):
    max_daily_parameter_changes: int = Field(default=1, ge=1)
    max_parameter_change_pct: float = Field(default=0.20, gt=0, le=1)
    cooldown_after_disable_hours: int = 48


class TournamentStageConfig(BaseModel):
    min_sharpe: float = 1.5
    min_trades: int = 50
    max_drawdown: float = 0.15
    min_win_rate: float = 0.45


class LiveLimitedConfig(BaseModel):
    max_capital_pct: float = 0.10
    max_capital_usd: float = 500.0


class TournamentConfig(BaseModel):
    enabled: bool = False
    evaluate_cron: str = "0 * * * *"
    stages: dict[int, TournamentStageConfig] = Field(default_factory=dict)
    live_limited: LiveLimitedConfig = Field(default_factory=LiveLimitedConfig)


class DeepReflectionConfig(BaseModel):
    pnl_multiplier: float = 2.0  # abs(pnl) > pnl_multiplier × expected → deep
    loss_multiplier: float = 1.5  # loss > loss_multiplier × stop → deep


class PreTradeQueryConfig(BaseModel):
    enabled: bool = True
    top_k: int = 5


class MemoryConfig(BaseModel):
    enabled: bool = False
    deep_reflection: DeepReflectionConfig = Field(default_factory=DeepReflectionConfig)
    ttl_days: int = 90
    pre_trade_query: PreTradeQueryConfig = Field(default_factory=PreTradeQueryConfig)


class ConfidenceCalibrationConfig(BaseModel):
    enabled: bool = True
    bucket_width: float = Field(default=0.10, gt=0, le=1)
    min_trades_for_usable_bucket: int = Field(default=25, ge=1)
    min_trades_for_hard_reject: int = Field(default=50, ge=1)
    insufficient_sample_multiplier: float = Field(default=0.75, gt=0, le=2)
    max_positive_multiplier: float = Field(default=1.25, gt=0, le=2)
    max_composed_kelly_fraction: float = Field(default=0.50, gt=0, le=1)
    weak_expectancy_threshold: float = Field(default=0.005, ge=0)
    moderate_expectancy_threshold: float = Field(default=0.015, ge=0)
    strong_expectancy_threshold: float = Field(default=0.03, ge=0)
    allow_reject: bool = False


class StrategyHealthConfig(BaseModel):
    """Configuration for strategy health evaluation and throttling."""

    enabled: bool = True
    default_window_trades: int = Field(default=50, ge=1)
    default_expectancy_floor: float = 0.0
    default_drawdown_limit: float = 5000.0
    default_min_trade_count: int = Field(default=20, ge=1)
    cooldown_hours: int = Field(default=24, ge=0)
    recovery_window_trades: int = Field(default=30, ge=1)
    throttle_multiplier: float = Field(default=0.5, gt=0, le=1)
    retire_after_breaches: int = Field(default=3, ge=1)


class LearningConfig(BaseModel):
    pnl: PnlConfig = Field(default_factory=PnlConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    optimization: OptimizationConfig = Field(default_factory=OptimizationConfig)
    reflection: ReflectionConfig = Field(default_factory=ReflectionConfig)
    guardrails: GuardrailsConfig = Field(default_factory=GuardrailsConfig)
    triggers: dict[str, Any] = Field(default_factory=dict)
    tournament: TournamentConfig = Field(default_factory=TournamentConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    confidence_calibration: ConfidenceCalibrationConfig = Field(
        default_factory=ConfidenceCalibrationConfig
    )
    strategy_health: StrategyHealthConfig = Field(default_factory=StrategyHealthConfig)


def load_learning_config(data: dict) -> LearningConfig:
    return LearningConfig(**data)
