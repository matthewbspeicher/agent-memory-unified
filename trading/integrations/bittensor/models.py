from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawMinerForecast:
    window_id: str
    request_uuid: str
    collected_at: datetime
    miner_uid: int | None
    miner_hotkey: str
    stream_id: str
    topic_id: int
    schema_id: int
    symbol: str
    timeframe: str
    feature_ids: list[int]
    prediction_size: int
    predictions: list[float]
    hashed_predictions: str | None
    hash_verified: bool
    incentive_score: float | None = None
    vtrust: float | None = None
    stake_tao: float | None = None
    metagraph_block: int | None = None


@dataclass
class DerivedMinerSignal:
    """Ephemeral per-miner summary. Not persisted — used to compute DerivedBittensorView."""

    window_id: str
    miner_hotkey: str
    symbol: str
    timeframe: str
    direction: str  # "long" | "short" | "flat"
    expected_return: float
    path_slope: float
    volatility_proxy: float
    confidence_proxy: float
    timestamp: datetime


@dataclass
class DerivedBittensorView:
    """Persisted aggregate consensus view. The shape agents consume."""

    symbol: str
    timeframe: str
    window_id: str
    timestamp: datetime
    responder_count: int
    bullish_count: int
    bearish_count: int
    flat_count: int
    weighted_direction: float
    weighted_expected_return: float
    agreement_ratio: float
    equal_weight_direction: float
    equal_weight_expected_return: float
    is_low_confidence: bool
    derivation_version: str


@dataclass
class RealizedWindowSnapshot:
    window_id: str
    symbol: str
    timeframe: str
    realized_path: list[float]
    realized_return: float
    bars_used: int
    source: str
    captured_at: datetime


@dataclass
class MinerAccuracyRecord:
    window_id: str
    miner_hotkey: str
    symbol: str
    timeframe: str
    direction_correct: bool
    predicted_return: float
    actual_return: float
    magnitude_error: float
    path_correlation: float | None
    outcome_bars: int
    scoring_version: str
    evaluated_at: datetime


@dataclass
class MinerRanking:
    miner_hotkey: str
    windows_evaluated: int
    direction_accuracy: float
    mean_magnitude_error: float
    mean_path_correlation: float | None
    internal_score: float
    latest_incentive_score: float | None
    hybrid_score: float
    alpha_used: float
    updated_at: datetime


@dataclass
class BittensorEvaluationWindow:
    """Returned by store when querying mature unevaluated windows."""

    window_id: str
    symbol: str
    timeframe: str
    collected_at: datetime
    prediction_size: int


@dataclass
class PredictionRequest:
    """Wire-compatible request shape for Taoshi Subnet 8 queries."""

    stream_id: str = "BTCUSD-5m"
    topic_id: int = 1
    schema_id: int = 1
    feature_ids: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])
    prediction_size: int = 100


@dataclass
class MinerRankingInput:
    """Pre-loaded input for the pure ranking function. No store/metagraph dependencies."""

    miner_hotkey: str
    windows_evaluated: int
    direction_accuracy: float  # [0, 1] from rollup
    mean_magnitude_error: float  # [0, ∞) from rollup
    mean_path_correlation: float | None  # [-1, 1] or None if insufficient data
    raw_incentive_score: (
        float  # raw value from metagraph; normalized inside compute_rankings()
    )


@dataclass
class RankingWeights:
    """Component weights for internal score computation."""

    direction: float
    magnitude: float
    path: float


@dataclass
class RankingConfig:
    """Configuration for ranking computation."""

    min_windows_for_ranking: int
    alpha_decay_per_window: float
    alpha_floor: float
    lookback_windows: int


@dataclass
class BittensorMetrics:
    """Observable metrics for Bittensor subsystem health."""

    # Scheduler metrics
    windows_collected: int = 0
    windows_failed: int = 0
    hash_verifications_passed: int = 0
    hash_verifications_failed: int = 0
    last_collection_duration_secs: float = 0.0
    avg_collection_duration_secs: float = 0.0
    last_miner_response_rate: float = 0.0

    # Evaluator metrics
    windows_evaluated: int = 0
    windows_expired: int = 0
    windows_skipped_no_data: int = 0
    last_evaluation_duration_secs: float = 0.0

    # Weight setter metrics
    weight_sets_total: int = 0
    weight_sets_failed: int = 0
    last_weight_set_block: int | None = None

    # Connection health
    connection_failures: int = 0
    last_connection_failure_at: datetime | None = None
    metagraph_refreshes: int = 0
    consecutive_failures: int = 0
