# strategies/multi_timeframe_consensus.py
from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from agents.base import StructuredAgent
from agents.models import Opportunity
from broker.models import Symbol
from data.bus import DataBus
from data.indicators import compute_rsi, compute_macd, compute_ema

logger = logging.getLogger(__name__)


class TimeframeDirection(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class TimeframeSignal:
    timeframe: str
    direction: TimeframeDirection
    rsi: float
    macd_histogram: float
    ema_trend: str  # "above" or "below" price
    weight: float


# Default timeframe weights (higher = more influence)
DEFAULT_TIMEFRAME_WEIGHTS: dict[str, float] = {
    "5m": 0.5,
    "15m": 1.0,
    "1h": 1.5,
    "4h": 2.0,
    "1d": 3.0,
}

# Default timeframe configs: (timeframe, bar_period, bar_interval)
DEFAULT_TIMEFRAME_CONFIGS: list[tuple[str, str, str]] = [
    ("5m", "1d", "5m"),
    ("15m", "5d", "15m"),
    ("1h", "1mo", "1h"),
    ("4h", "3mo", "4h"),
    ("1d", "6mo", "1d"),
]


class MultiTimeframeConsensusAgent(StructuredAgent):
    """Generates opportunities only when multiple timeframes agree on direction.

    Parameters:
        min_consensus: Minimum weighted consensus ratio (0-1) to trigger. Default 0.7.
        rsi_overbought: RSI level considered overbought. Default 70.
        rsi_oversold: RSI level considered oversold. Default 30.
        timeframe_weights: Dict mapping timeframe -> weight. Uses DEFAULT_TIMEFRAME_WEIGHTS.
        timeframe_configs: List of (timeframe, period, interval). Uses DEFAULT_TIMEFRAME_CONFIGS.
        min_timeframes_agree: Minimum absolute count of timeframes that must agree. Default 3.
    """

    @property
    def description(self) -> str:
        min_c = self.parameters.get("min_consensus", 0.7)
        return f"Multi-timeframe consensus scanner (min_consensus={min_c})"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        params = self.parameters
        min_consensus = params.get("min_consensus", 0.7)
        rsi_overbought = params.get("rsi_overbought", 70)
        rsi_oversold = params.get("rsi_oversold", 30)
        min_timeframes_agree = params.get("min_timeframes_agree", 3)

        timeframe_weights = params.get("timeframe_weights", DEFAULT_TIMEFRAME_WEIGHTS)
        timeframe_configs = params.get("timeframe_configs", DEFAULT_TIMEFRAME_CONFIGS)

        # Normalize timeframe_configs if they come from YAML (list of lists)
        t_configs: list[tuple[str, str, str]] = []
        for tc in timeframe_configs:
            if isinstance(tc, list) and len(tc) == 3:
                t_configs.append((str(tc[0]), str(tc[1]), str(tc[2])))
            elif isinstance(tc, dict):
                t_configs.append((tc["timeframe"], tc["period"], tc["interval"]))
            else:
                t_configs.append(tc)

        symbols = data.get_universe(self.universe)
        opportunities: list[Opportunity] = []

        for symbol in symbols:
            try:
                signals = await self._analyze_timeframes(
                    data,
                    symbol,
                    t_configs,
                    timeframe_weights,
                    rsi_overbought,
                    rsi_oversold,
                )
            except Exception as e:
                logger.warning(
                    "Multi-timeframe scan failed for %s: %s", symbol.ticker, e
                )
                continue

            opp = self._check_consensus(
                symbol,
                signals,
                min_consensus,
                min_timeframes_agree,
            )
            if opp:
                opportunities.append(opp)

        return opportunities

    async def _analyze_timeframes(
        self,
        data: DataBus,
        symbol: Symbol,
        t_configs: list[tuple[str, str, str]],
        weights: dict[str, float],
        rsi_overbought: float,
        rsi_oversold: float,
    ) -> list[TimeframeSignal]:
        signals: list[TimeframeSignal] = []

        for tf, period, interval in t_configs:
            try:
                bars = await data.get_historical(symbol, interval, period)
                if len(bars) < 30:
                    logger.debug(
                        "Skipping %s %s: insufficient bars (%d)",
                        symbol.ticker,
                        tf,
                        len(bars),
                    )
                    continue

                rsi = compute_rsi(bars, 14)
                macd = compute_macd(bars)
                last_close = float(bars[-1].close)
                ema_20 = compute_ema(bars, 20)
                ema_trend = "above" if last_close > ema_20 else "below"

                direction = self._classify_direction(
                    rsi, macd.histogram, ema_trend, rsi_overbought, rsi_oversold
                )

                signals.append(
                    TimeframeSignal(
                        timeframe=tf,
                        direction=direction,
                        rsi=rsi,
                        macd_histogram=macd.histogram,
                        ema_trend=ema_trend,
                        weight=weights.get(tf, 1.0),
                    )
                )
            except Exception as e:
                logger.debug("Timeframe %s failed for %s: %s", tf, symbol.ticker, e)
                continue

        return signals

    def _classify_direction(
        self,
        rsi: float,
        macd_hist: float,
        ema_trend: str,
        rsi_overbought: float,
        rsi_oversold: float,
    ) -> TimeframeDirection:
        """Classify direction using majority vote of 3 indicators."""
        votes_bullish = 0
        votes_bearish = 0

        # RSI vote
        if rsi < rsi_oversold:
            votes_bullish += 1
        elif rsi > rsi_overbought:
            votes_bearish += 1

        # MACD histogram vote
        if macd_hist > 0:
            votes_bullish += 1
        elif macd_hist < 0:
            votes_bearish += 1

        # EMA trend vote
        if ema_trend == "above":
            votes_bullish += 1
        else:
            votes_bearish += 1

        if votes_bullish >= 2:
            return TimeframeDirection.BULLISH
        elif votes_bearish >= 2:
            return TimeframeDirection.BEARISH
        return TimeframeDirection.NEUTRAL

    def _check_consensus(
        self,
        symbol: Symbol,
        signals: list[TimeframeSignal],
        min_consensus: float,
        min_timeframes_agree: int,
    ) -> Opportunity | None:
        if not signals:
            return None

        total_weight = sum(s.weight for s in signals)
        if total_weight == 0:
            return None

        # Count bullish and bearish weighted consensus
        bullish_weight = sum(
            s.weight for s in signals if s.direction == TimeframeDirection.BULLISH
        )
        bearish_weight = sum(
            s.weight for s in signals if s.direction == TimeframeDirection.BEARISH
        )
        bullish_count = sum(
            1 for s in signals if s.direction == TimeframeDirection.BULLISH
        )
        bearish_count = sum(
            1 for s in signals if s.direction == TimeframeDirection.BEARISH
        )

        bullish_ratio = bullish_weight / total_weight
        bearish_ratio = bearish_weight / total_weight

        direction = None
        consensus_ratio = 0.0
        agreeing_count = 0

        if bullish_ratio >= min_consensus and bullish_count >= min_timeframes_agree:
            direction = "BULLISH"
            consensus_ratio = bullish_ratio
            agreeing_count = bullish_count
        elif bearish_ratio >= min_consensus and bearish_count >= min_timeframes_agree:
            direction = "BEARISH"
            consensus_ratio = bearish_ratio
            agreeing_count = bearish_count

        if direction is None:
            return None

        # Build reasoning
        agreeing_tfs = [
            s.timeframe
            for s in signals
            if (
                (direction == "BULLISH" and s.direction == TimeframeDirection.BULLISH)
                or (
                    direction == "BEARISH" and s.direction == TimeframeDirection.BEARISH
                )
            )
        ]
        neutral_tfs = [
            s.timeframe for s in signals if s.direction == TimeframeDirection.NEUTRAL
        ]

        avg_rsi = sum(s.rsi for s in signals) / len(signals)
        avg_macd = sum(s.macd_histogram for s in signals) / len(signals)

        reasoning = (
            f"{symbol.ticker} {direction} consensus: {consensus_ratio:.0%} "
            f"({agreeing_count}/{len(signals)} timeframes agree). "
            f"Agreeing: {','.join(agreeing_tfs)}. "
            f"Neutral: {','.join(neutral_tfs) if neutral_tfs else 'none'}. "
            f"Avg RSI={avg_rsi:.1f}, Avg MACD hist={avg_macd:.4f}"
        )

        signal_name = f"MTF_CONSENSUS_{direction}"
        # Confidence scales from min_consensus to 1.0
        confidence = min(
            (consensus_ratio - min_consensus) / (1.0 - min_consensus) + 0.5, 1.0
        )

        return Opportunity(
            id=str(uuid.uuid4()),
            agent_name=self.name,
            symbol=symbol,
            signal=signal_name,
            confidence=confidence,
            reasoning=reasoning,
            data={
                "direction": direction,
                "consensus_ratio": consensus_ratio,
                "agreeing_count": agreeing_count,
                "total_timeframes": len(signals),
                "agreeing_timeframes": agreeing_tfs,
                "avg_rsi": avg_rsi,
                "avg_macd_histogram": avg_macd,
                "signals": [
                    {
                        "timeframe": s.timeframe,
                        "direction": s.direction.value,
                        "rsi": round(s.rsi, 2),
                        "macd_histogram": round(s.macd_histogram, 4),
                        "ema_trend": s.ema_trend,
                        "weight": s.weight,
                    }
                    for s in signals
                ],
            },
            timestamp=datetime.now(timezone.utc),
        )
