from dataclasses import dataclass, field


@dataclass
class IntelligenceConfig:
    """Configuration for the Market Intelligence Layer."""

    enabled: bool = False
    timeout_ms: int = 2000
    min_providers: int = 1
    veto_threshold: int = 1  # 1=any, 2=majority
    weights: dict[str, float] = field(default_factory=lambda: {
        "on_chain": 0.15,
        "sentiment": 0.10,
        "anomaly": 0.05,
    })
    max_adjustment_pct: float = 0.30
    stale_data_threshold_seconds: int = 300
    circuit_breaker_failures: int = 3
    circuit_breaker_reset_seconds: int = 60

    # API keys (all optional -- providers degrade gracefully)
    coinglass_api_key: str | None = None
    glassnode_api_key: str | None = None
    lunarcrush_api_key: str | None = None
    santiment_api_key: str | None = None
