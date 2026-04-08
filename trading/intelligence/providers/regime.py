from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import joblib
import numpy as np
import pandas as pd

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider

if TYPE_CHECKING:
    from memory.market_regime import RegimeMemoryManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HMM Regime Detection
# ---------------------------------------------------------------------------

REGIME_STATES = {
    0: "trending_bull",
    1: "trending_bear",
    2: "volatile",
    3: "quiet",
}


def extract_hmm_features(df: pd.DataFrame) -> np.ndarray:
    """Extract feature matrix for HMM from OHLCV data."""
    data = df.copy()
    data["log_return"] = np.log(data["close"] / data["close"].shift(1))
    data["realized_vol_20d"] = data["log_return"].rolling(20).std() * np.sqrt(365)
    vol_mean = data["volume"].rolling(20).mean()
    vol_std = data["volume"].rolling(20).std()
    data["volume_zscore"] = (data["volume"] - vol_mean) / vol_std.replace(0, 1)
    if "funding_rate" not in data.columns:
        data["funding_rate"] = 0.0
    else:
        data["funding_rate"] = data["funding_rate"].fillna(0)
    feature_cols = ["log_return", "realized_vol_20d", "volume_zscore", "funding_rate"]
    return data[feature_cols].dropna().values


class StableRegimeDetector:
    """Hysteresis wrapper — requires sustained state change before transition."""

    def __init__(self, min_state_duration: int = 3):
        self.min_state_duration = min_state_duration
        self.current_state: int | None = None
        self.state_age: int = 0
        self.pending_state: int | None = None
        self.pending_age: int = 0

    def update(self, raw_state: int) -> tuple[int | None, bool]:
        if self.current_state is None:
            if self.pending_state == raw_state:
                self.pending_age += 1
            else:
                self.pending_state = raw_state
                self.pending_age = 1
            if self.pending_age >= self.min_state_duration:
                self.current_state = raw_state
                self.state_age = self.pending_age
                self.pending_state = None
                self.pending_age = 0
                return self.current_state, False
            return None, False

        if raw_state == self.current_state:
            self.state_age += 1
            self.pending_state = None
            self.pending_age = 0
            return self.current_state, False

        if raw_state == self.pending_state:
            self.pending_age += 1
        else:
            self.pending_state = raw_state
            self.pending_age = 1

        if self.pending_age >= self.min_state_duration:
            self.current_state = self.pending_state
            self.state_age = self.pending_age
            self.pending_state = None
            self.pending_age = 0
            return self.current_state, True

        return self.current_state, False


class RegimeProvider(BaseIntelProvider):
    """Uses RegimeMemoryManager to provide historical regime context.

    Score is always 0 (regime doesn't dictate direction), but confidence
    increases when many similar historical regimes are found in memory.
    This acts as a conviction multiplier — familiar regimes get higher trust.
    """

    def __init__(self, memory_manager: "RegimeMemoryManager | None" = None):
        self.memory_manager = memory_manager

    @property
    def name(self) -> str:
        return "regime"

    async def analyze(self, symbol: str) -> IntelReport | None:
        if not self.memory_manager:
            return None

        try:
            bars = await self._fetch_bars(symbol)
            if not bars or len(bars) < 2:
                return None

            regime = self.memory_manager.detect_regime(bars)

            from broker.models import Symbol as SymbolModel

            memories = await self.memory_manager.recall_similar_regimes(
                SymbolModel(ticker=symbol), regime
            )

            # Conviction boost: more historical parallels = higher confidence
            confidence = min(0.5 + (len(memories) * 0.1), 1.0)

            # Store current regime for future recall (fire-and-forget)
            try:
                await self.memory_manager.store_regime(
                    SymbolModel(ticker=symbol),
                    regime,
                    {"volatility": self._calc_volatility(bars)},
                )
            except Exception:
                pass  # non-critical

            return IntelReport(
                source=self.name,
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                score=0.0,  # regime doesn't dictate direction
                confidence=confidence,
                veto=False,
                veto_reason=None,
                details={
                    "regime": regime,
                    "recalled_count": len(memories),
                },
            )
        except Exception as e:
            logger.warning("RegimeProvider failed for %s: %s", symbol, e)
            return None

    async def _fetch_bars(self, symbol: str) -> list:
        """Fetch recent price bars. Override in tests."""
        try:
            import ccxt.async_support as ccxt

            exchange = ccxt.binance()
            try:
                from broker.models import Bar, Symbol as SymbolModel, AssetType
                from decimal import Decimal

                ticker_map = {"BTCUSD": "BTC/USDT", "ETHUSD": "ETH/USDT"}
                ccxt_symbol = ticker_map.get(symbol, symbol.replace("USD", "/USDT"))
                ohlcv = await exchange.fetch_ohlcv(ccxt_symbol, "1h", limit=120)

                bars = []
                for candle in ohlcv:
                    ts = datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc)
                    bars.append(
                        Bar(
                            symbol=SymbolModel(
                                ticker=symbol, asset_type=AssetType.CRYPTO
                            ),
                            timestamp=ts,
                            close=Decimal(str(candle[4])),
                        )
                    )
                return bars
            finally:
                await exchange.close()
        except ImportError:
            raise NotImplementedError("Install ccxt: pip install ccxt")

    @staticmethod
    def _calc_volatility(bars: list) -> float:
        prices = [float(b.close) for b in bars]
        if len(prices) < 2:
            return 0.0
        returns = [
            (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))
        ]
        avg = sum(returns) / len(returns)
        return (sum((r - avg) ** 2 for r in returns) / len(returns)) ** 0.5
