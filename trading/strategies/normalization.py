"""
NormalizedContract — comparable probability + liquidity representation.

Normalises PredictionContract fields from Kalshi and Polymarket into
a unified view used by CrossPlatformArbAgent and SpreadTracker.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from broker.models import PredictionContract
from strategies.matching import normalize_category


@dataclass(frozen=True)
class NormalizedContract:
    ticker: str
    platform: Literal["kalshi", "polymarket"]
    title: str
    category: str                   # normalised category string
    close_time: datetime
    mid_prob: float                 # 0.0–1.0, best available mid
    bid_prob: float | None          # 0.0–1.0
    ask_prob: float | None          # 0.0–1.0
    spread_prob: float | None       # ask_prob - bid_prob, or None
    volume_usd_24h: float           # always in USD notional
    liquidity_score: float          # 0.0–1.0 composite


def _mid(bid: int | None, ask: int | None, last: int | None) -> float:
    """Best-effort mid probability (0.0–1.0)."""
    if bid is not None and ask is not None:
        return (bid + ask) / 2 / 100
    if last is not None:
        return last / 100
    if bid is not None:
        return bid / 100
    return 0.5  # fallback: maximum uncertainty


def _liquidity_score(volume_usd: float, spread_prob: float | None) -> float:
    """Composite 0-1 liquidity score from log-normalised volume and spread."""
    # Log-normalise volume: $10 → ~0.1, $100k → ~0.5, $10M → ~0.8
    vol_score = min(1.0, math.log10(max(volume_usd, 1)) / 8.0)
    if spread_prob is not None:
        tightness = max(0.0, 1.0 - spread_prob)
        return min(1.0, (vol_score + tightness) / 2)
    return vol_score


def normalize_contract(
    c: PredictionContract,
    platform: Literal["kalshi", "polymarket"],
) -> NormalizedContract:
    bid_prob = c.yes_bid / 100 if c.yes_bid is not None else None
    ask_prob = c.yes_ask / 100 if c.yes_ask is not None else None
    spread_prob = (ask_prob - bid_prob) if (bid_prob is not None and ask_prob is not None) else None
    mid = _mid(c.yes_bid, c.yes_ask, c.yes_last)

    # Volume normalisation
    if platform == "kalshi":
        # contracts × mid price → USD notional; if no quotes, can't estimate → 0
        if c.yes_bid is None and c.yes_ask is None and c.yes_last is None:
            volume_usd = 0.0
        else:
            volume_usd = c.volume_24h * mid
    else:
        # Polymarket volume_24h is already USD notional
        volume_usd = float(c.volume_24h)

    return NormalizedContract(
        ticker=c.ticker,
        platform=platform,
        title=c.title,
        category=normalize_category(c.category),
        close_time=c.close_time if isinstance(c.close_time, datetime)
            else datetime.fromisoformat(str(c.close_time).replace("Z", "+00:00")),
        mid_prob=mid,
        bid_prob=bid_prob,
        ask_prob=ask_prob,
        spread_prob=spread_prob,
        volume_usd_24h=volume_usd,
        liquidity_score=_liquidity_score(volume_usd, spread_prob),
    )


def compute_confidence(
    gap_cents: int,
    k_norm: NormalizedContract,
    p_norm: NormalizedContract,
) -> float:
    """
    Confidence proportional to spread size and market liquidity.

    gap_prob * 2 gives 1.0 at 50¢ gap; capped at 0.9.
    liq_weight blends both sides' liquidity so thin markets discount the signal.
    """
    gap_prob = gap_cents / 100
    liq_weight = (k_norm.liquidity_score + p_norm.liquidity_score) / 2
    confidence = round(min(gap_prob * 2, 0.9) * (0.5 + 0.5 * liq_weight), 3)
    return confidence
