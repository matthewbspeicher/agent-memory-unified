from __future__ import annotations
from pydantic import BaseModel, Field


class IntelligenceConfig(BaseModel):
    """Configuration for the Market Intelligence Layer."""

    enabled: bool = False
    timeout_ms: int = 2000
    min_providers: int = 1
    veto_threshold: int = 1  # 1=any, 2=majority
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "on_chain": 0.15,
            "sentiment": 0.10,
            "anomaly": 0.05,
            "order_flow": 0.12,
            "regime": 0.10,
            "risk_audit": 0.05,
            "derivatives": 0.12,
            "knowledge_graph": 0.15,
        }
    )
    risk_var_threshold_pct: float = 5.0
    risk_horizon_days: int = 5
    max_adjustment_pct: float = 0.30
    stale_data_threshold_seconds: int = 300
    circuit_breaker_failures: int = 3
    circuit_breaker_reset_seconds: int = 60

    # API keys (all optional — providers degrade gracefully)
    coinglass_api_key: str | None = None
    glassnode_api_key: str | None = None
    lunarcrush_api_key: str | None = None
    santiment_api_key: str | None = None

    # Equity sentiment poller (ADR-0011 follow-up).
    # Drives the `intel_sentiment` topic on a configured equity universe so
    # personas like Buffett/Graham/Lynch — whose universe contains AAPL/MSFT
    # etc., not BTCUSD/ETHUSD — actually receive sentiment data.  Off by
    # default (empty list).  Setting equity_sentiment_universe enables the
    # background poller in `IntelligenceLayer.start()`.
    equity_sentiment_universe: list[str] = Field(default_factory=list)
    equity_sentiment_interval_seconds: int = 900  # 15 minutes
    equity_sentiment_max_concurrency: int = 3
