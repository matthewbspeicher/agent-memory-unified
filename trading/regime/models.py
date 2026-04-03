"""Market regime models."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class MarketRegime(str, Enum):
    """Current market regime classification."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


@dataclass
class RegimeSnapshot:
    """A detected regime with supporting indicator values."""
    regime: MarketRegime
    detected_at: datetime
    adx: float | None = None          # Average Directional Index (trend strength)
    volatility_pct: float | None = None  # Annualized volatility estimate
    sma_slope: float | None = None    # Slope of 50-bar SMA (normalized)
    bars_analyzed: int = 0
    economic_data: dict | None = None  # Supplementary Alpha Vantage data (GDP, Fed rate)

    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "detected_at": self.detected_at.isoformat(),
            "adx": self.adx,
            "volatility_pct": self.volatility_pct,
            "sma_slope": self.sma_slope,
            "bars_analyzed": self.bars_analyzed,
            "economic_data": self.economic_data,
        }


class LiquidityRegime(str, Enum):
    """Liquidity regime classification for a specific prediction market symbol."""
    FAVORABLE = "FAVORABLE"
    UNFAVORABLE = "UNFAVORABLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class LiquiditySnapshot:
    """A detected liquidity regime with supporting market data for a specific symbol."""
    regime: LiquidityRegime
    spread_cents: float        # bid-ask spread for this symbol in cents
    volume_24h: float          # 24h volume
    symbol: str                # which symbol this is for
    detected_at: datetime

    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "spread_cents": self.spread_cents,
            "volume_24h": self.volume_24h,
            "symbol": self.symbol,
            "detected_at": self.detected_at.isoformat(),
        }
