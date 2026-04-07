from __future__ import annotations

from pydantic import BaseModel


# --- /api/bittensor/status ---


class SchedulerStatus(BaseModel):
    running: bool
    last_window_collected: str | None = None
    next_window: str
    windows_collected_total: int


class EvaluatorStatus(BaseModel):
    running: bool
    last_evaluation: str | None = None
    unevaluated_windows: int
    windows_evaluated_total: int


class TopMinerItem(BaseModel):
    hotkey: str
    hybrid_score: float
    direction_accuracy: float
    windows_evaluated: int


class MinerSummary(BaseModel):
    total_in_metagraph: int
    responded_last_window: int
    response_rate: float
    top_miners: list[TopMinerItem]


class AgentSummary(BaseModel):
    name: str
    opportunities_emitted: int
    last_opportunity: str | None = None


class BridgeStatus(BaseModel):
    running: bool
    taoshi_root: str
    miners_tracked: int
    open_positions: int
    signals_emitted: int
    last_scan_at: str | None = None
    seen_positions: int


class BittensorStatusResponse(BaseModel):
    enabled: bool
    healthy: bool | None = None
    scheduler: SchedulerStatus | None = None
    evaluator: EvaluatorStatus | None = None
    miners: MinerSummary | None = None
    agent: AgentSummary | None = None
    bridge: BridgeStatus | None = None


# --- /api/bittensor/metrics ---


class SchedulerMetrics(BaseModel):
    windows_collected: int
    windows_failed: int
    hash_verifications_passed: int
    hash_verifications_failed: int
    last_collection_duration_secs: float
    avg_collection_duration_secs: float
    last_miner_response_rate: float
    consecutive_failures: int


class EvaluatorMetrics(BaseModel):
    windows_evaluated: int
    windows_expired: int
    windows_skipped: int
    last_skip_reason: str | None = None
    last_evaluation_duration_secs: float


class WeightSetterMetrics(BaseModel):
    weight_sets_total: int
    weight_sets_failed: int
    last_weight_set_block: int | None = None


class BittensorMetricsResponse(BaseModel):
    enabled: bool
    scheduler: SchedulerMetrics | None = None
    evaluator: EvaluatorMetrics | None = None
    weight_setter: WeightSetterMetrics | None = None


# --- /api/bittensor/rankings ---


class MinerRankingItem(BaseModel):
    miner_hotkey: str
    hybrid_score: float
    direction_accuracy: float
    mean_magnitude_error: float
    mean_path_correlation: float | None = None
    internal_score: float
    latest_incentive_score: float | None = None
    windows_evaluated: int
    alpha_used: float
    updated_at: str


class BittensorRankingsResponse(BaseModel):
    rankings: list[MinerRankingItem]
    ranking_config: dict


# --- /api/bittensor/miners/{hotkey}/accuracy ---


class AccuracyRecordItem(BaseModel):
    window_id: str
    symbol: str
    timeframe: str
    direction_correct: bool
    predicted_return: float
    actual_return: float
    magnitude_error: float
    path_correlation: float | None = None
    outcome_bars: int
    scoring_version: str
    evaluated_at: str


class MinerAccuracyResponse(BaseModel):
    hotkey: str
    records: list[AccuracyRecordItem]


# --- /api/bittensor/signals ---


class BittensorSignalsResponse(BaseModel):
    signals: list[dict]
