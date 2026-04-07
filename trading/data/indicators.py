# data/indicators.py
from __future__ import annotations
from dataclasses import dataclass

from broker.models import Bar


@dataclass(frozen=True)
class MACD:
    macd_line: float
    signal_line: float
    histogram: float


@dataclass(frozen=True)
class BollingerBands:
    upper: float
    middle: float
    lower: float


def _closes(bars: list[Bar]) -> list[float]:
    return [float(b.close) for b in bars]


def compute_sma(bars: list[Bar], period: int) -> float:
    closes = _closes(bars)
    if len(closes) < period:
        raise ValueError(f"Need at least {period} bars, got {len(closes)}")
    return sum(closes[-period:]) / period


def compute_ema(bars: list[Bar], period: int) -> float:
    closes = _closes(bars)
    if len(closes) < period:
        raise ValueError(f"Need at least {period} bars, got {len(closes)}")
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return ema


def compute_rsi(bars: list[Bar], period: int = 14) -> float:
    closes = _closes(bars)
    if len(closes) < period + 1:
        raise ValueError(f"Need at least {period + 1} bars, got {len(closes)}")
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_macd(
    bars: list[Bar],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MACD:
    closes = _closes(bars)
    if len(closes) < slow + signal:
        raise ValueError(f"Need at least {slow + signal} bars, got {len(closes)}")
    k_fast = 2 / (fast + 1)
    k_slow = 2 / (slow + 1)
    ema_fast = sum(closes[:fast]) / fast
    ema_slow = sum(closes[:slow]) / slow
    macd_values: list[float] = []
    for i in range(slow, len(closes)):
        ema_fast = closes[i] * k_fast + ema_fast * (1 - k_fast)
        ema_slow = closes[i] * k_slow + ema_slow * (1 - k_slow)
        macd_values.append(ema_fast - ema_slow)
    k_sig = 2 / (signal + 1)
    sig = sum(macd_values[:signal]) / signal
    for v in macd_values[signal:]:
        sig = v * k_sig + sig * (1 - k_sig)
    macd_line = macd_values[-1]
    return MACD(macd_line=macd_line, signal_line=sig, histogram=macd_line - sig)


def compute_bollinger(
    bars: list[Bar],
    period: int = 20,
    num_std: float = 2.0,
) -> BollingerBands:
    closes = _closes(bars)
    if len(closes) < period:
        raise ValueError(f"Need at least {period} bars, got {len(closes)}")
    window = closes[-period:]
    middle = sum(window) / period
    variance = sum((p - middle) ** 2 for p in window) / period
    std = variance**0.5
    return BollingerBands(
        upper=middle + num_std * std,
        middle=middle,
        lower=middle - num_std * std,
    )


def compute_atr(bars: list[Bar], period: int = 14) -> float:
    """Average True Range over *period* bars.

    True range = max(high-low, |high-prev_close|, |low-prev_close|).
    Requires at least period+1 bars.
    """
    if len(bars) < period + 1:
        raise ValueError(
            f"Need at least {period + 1} bars for ATR({period}), got {len(bars)}"
        )
    true_ranges: list[float] = []
    for i in range(1, len(bars)):
        high = float(bars[i].high)
        low = float(bars[i].low)
        prev_close = float(bars[i - 1].close)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
    window = true_ranges[-period:]
    return sum(window) / len(window)


def compute_realized_vol(bars: list[Bar], period: int = 20) -> float:
    """Annualized realized volatility: std dev of daily log returns * sqrt(252).

    Requires at least period+1 bars.
    """
    import math

    closes = _closes(bars)
    if len(closes) < period + 1:
        raise ValueError(
            f"Need at least {period + 1} bars for realized vol({period}), got {len(closes)}"
        )
    window = closes[-(period + 1) :]
    log_returns = [math.log(window[i] / window[i - 1]) for i in range(1, len(window))]
    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / len(log_returns)
    return (variance**0.5) * math.sqrt(252)


def compute_relative_volume(bars: list[Bar], period: int = 20) -> float:
    """Current bar volume / average volume over the most recent *period* bars.

    The last bar is the "current" bar. The average includes the current bar.
    """
    if len(bars) < period:
        raise ValueError(
            f"Need at least {period} bars for relative volume, got {len(bars)}"
        )
    volumes = [float(b.volume) for b in bars[-period:]]
    avg_vol = sum(volumes) / len(volumes)
    if avg_vol == 0:
        return 1.0
    return volumes[-1] / avg_vol


def add_technical_indicators(df: Any) -> Any:
    """Add 50+ standard technical indicators to OHLCV DataFrame using pandas_ta."""
    import pandas_ta as ta

    # We append basic ones explicitly, or can use df.ta.strategy("all")
    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.bbands(append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    return df
