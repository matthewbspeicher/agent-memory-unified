from __future__ import annotations

from pydantic import BaseModel


# --- /api/bittensor/status ---


class SchedulerStatus(BaseModel):
    running: bool
    direct_query_enabled: bool = False
    last_window_collected: str | None = None
    next_window: str | None = None
    windows_collected_total: int | None = None


class TopMinerItem(BaseModel):
    hotkey: str
    hybrid_score: float
    direction_accuracy: float
    windows_evaluated: int


class MinerSummary(BaseModel):
    total_in_metagraph: int
    responded_last_window: int | None = None
    response_rate: float | None = None
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


class IntelProviderStatus(BaseModel):
    circuit: str
    failures: int


class IntelligenceStatus(BaseModel):
    enabled: bool
    providers: dict[str, IntelProviderStatus]
    enrichments_applied: int
    vetos_issued: int
    provider_failures: int
    total_calls: int


class BittensorStatusResponse(BaseModel):
    enabled: bool
    healthy: bool | None = None
    scheduler: SchedulerStatus | None = None
    miners: MinerSummary | None = None
    agent: AgentSummary | None = None
    bridge: BridgeStatus | None = None
    consensus_aggregator: dict[str, dict] | None = None
    intelligence: IntelligenceStatus | None = None


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
    weight_sets_skipped: int
    last_weight_skip_reason: str | None = None
    last_weight_set_block: int | None = None
    last_weight_set_at: str | None = None
    last_weight_set_uid_count: int | None = None


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


# --- /api/bittensor/signals ---


class BittensorSignalsResponse(BaseModel):
    signals: list[dict]
