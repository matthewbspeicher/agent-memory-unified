from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from decimal import Decimal

from agents.models import ActionLevel, AgentConfig
from broker.models import Bar, Symbol
from strategies.multi_timeframe_consensus import (
    MultiTimeframeConsensusAgent,
    TimeframeDirection,
)

TEST_SYMBOL = Symbol(ticker="AAPL")


def _make_config(**overrides):
    defaults = dict(
        name="mtf-test",
        strategy="multi_timeframe_consensus",
        schedule="on_demand",
        action_level=ActionLevel.NOTIFY,
        universe=["AAPL"],
        parameters={
            "min_consensus": 0.7,
            "min_timeframes_agree": 3,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
        },
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


def _make_bars(n: int, close_start: float, trend: str = "up") -> list[Bar]:
    """Generate synthetic bars for testing."""
    bars = []
    for i in range(n):
        if trend == "up":
            close = close_start + i * 0.5
        elif trend == "down":
            close = close_start - i * 0.5
        else:
            close = close_start + (0.5 if i % 2 == 0 else -0.5)
        bars.append(
            Bar(
                symbol=TEST_SYMBOL,
                timestamp=datetime.now(timezone.utc),
                open=Decimal(str(close - 0.25)),
                high=Decimal(str(close + 0.5)),
                low=Decimal(str(close - 0.5)),
                close=Decimal(str(close)),
                volume=1000000,
            )
        )
    return bars


class TestMultiTimeframeConsensusAgent:
    def test_description(self):
        agent = MultiTimeframeConsensusAgent(config=_make_config())
        assert "consensus" in agent.description.lower()

    async def test_scan_bullish_consensus(self):
        """All timeframes trending up should trigger BULLISH consensus."""
        bus = MagicMock()
        bus.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])

        # All timeframes return upward bars (bullish RSI, positive MACD, price > EMA)
        bus.get_historical = AsyncMock(
            side_effect=[
                _make_bars(100, 150.0, "up"),  # 5m
                _make_bars(100, 150.0, "up"),  # 15m
                _make_bars(100, 150.0, "up"),  # 1h
                _make_bars(100, 150.0, "up"),  # 4h
                _make_bars(100, 150.0, "up"),  # 1d
            ]
        )

        agent = MultiTimeframeConsensusAgent(config=_make_config())
        opps = await agent.scan(bus)

        assert len(opps) == 1
        assert opps[0].symbol.ticker == "AAPL"
        assert opps[0].signal == "MTF_CONSENSUS_BULLISH"
        assert opps[0].confidence > 0
        assert opps[0].data["agreeing_count"] == 5

    async def test_scan_bearish_consensus(self):
        """All timeframes trending down should trigger BEARISH consensus."""
        bus = MagicMock()
        bus.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])

        bus.get_historical = AsyncMock(
            side_effect=[
                _make_bars(100, 150.0, "down"),  # 5m
                _make_bars(100, 150.0, "down"),  # 15m
                _make_bars(100, 150.0, "down"),  # 1h
                _make_bars(100, 150.0, "down"),  # 4h
                _make_bars(100, 150.0, "down"),  # 1d
            ]
        )

        agent = MultiTimeframeConsensusAgent(config=_make_config())
        opps = await agent.scan(bus)

        assert len(opps) == 1
        assert opps[0].signal == "MTF_CONSENSUS_BEARISH"

    async def test_scan_no_consensus_mixed(self):
        """Mixed signals should not trigger."""
        bus = MagicMock()
        bus.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])

        # Alternate between up and down to create mixed signals
        bus.get_historical = AsyncMock(
            side_effect=[
                _make_bars(100, 150.0, "up"),  # 5m bullish
                _make_bars(100, 150.0, "down"),  # 15m bearish
                _make_bars(100, 150.0, "up"),  # 1h bullish
                _make_bars(100, 150.0, "down"),  # 4h bearish
                _make_bars(100, 150.0, "up"),  # 1d bullish
            ]
        )

        agent = MultiTimeframeConsensusAgent(config=_make_config())
        opps = await agent.scan(bus)

        # 3 bullish (5m, 1h, 1d) out of 5 = 60% < 70% threshold
        assert len(opps) == 0

    async def test_scan_insufficient_timeframes(self):
        """Should not trigger if fewer than min_timeframes_agree timeframes agree."""
        bus = MagicMock()
        bus.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])

        # Only 2 bearish timeframes (need 4)
        bus.get_historical = AsyncMock(
            side_effect=[
                _make_bars(100, 150.0, "up"),  # 5m bullish
                _make_bars(100, 150.0, "up"),  # 15m bullish
                _make_bars(100, 150.0, "up"),  # 1h bullish
                _make_bars(100, 150.0, "down"),  # 4h bearish
                _make_bars(100, 150.0, "down"),  # 1d bearish
            ]
        )

        config = _make_config(
            parameters={
                "min_consensus": 0.5,  # Lower threshold
                "min_timeframes_agree": 4,  # But need at least 4 agreeing
            }
        )
        agent = MultiTimeframeConsensusAgent(config=config)
        opps = await agent.scan(bus)

        # Only 3 bullish (5m,15m,1h) < 4 required, 2 bearish (4h,1d) < 4 required
        assert len(opps) == 0

    async def test_scan_handles_error_gracefully(self):
        """Errors on individual symbols should be logged, not raised."""
        bus = MagicMock()
        bus.get_universe = MagicMock(
            return_value=[
                Symbol(ticker="AAPL"),
                Symbol(ticker="BAD"),
            ]
        )
        bus.get_historical = AsyncMock(
            side_effect=[
                _make_bars(100, 150.0, "up"),
                _make_bars(100, 150.0, "up"),
                _make_bars(100, 150.0, "up"),
                _make_bars(100, 150.0, "up"),
                _make_bars(100, 150.0, "up"),
                Exception("data unavailable"),  # BAD symbol fails
            ]
        )

        agent = MultiTimeframeConsensusAgent(
            config=_make_config(universe=["AAPL", "BAD"])
        )
        opps = await agent.scan(bus)

        # AAPL should succeed, BAD should be skipped
        assert len(opps) == 1
        assert opps[0].symbol.ticker == "AAPL"

    async def test_scan_insufficient_bars_skipped(self):
        """Timeframes with insufficient bars should be skipped."""
        bus = MagicMock()
        bus.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])

        # Return bars with insufficient data for some timeframes
        bus.get_historical = AsyncMock(
            side_effect=[
                _make_bars(10, 150.0, "up"),  # 5m: too few bars (< 30)
                _make_bars(100, 150.0, "up"),  # 15m
                _make_bars(100, 150.0, "up"),  # 1h
                _make_bars(100, 150.0, "up"),  # 4h
                _make_bars(100, 150.0, "up"),  # 1d
            ]
        )

        agent = MultiTimeframeConsensusAgent(config=_make_config())
        opps = await agent.scan(bus)

        # 4 timeframes agree out of 4 valid = 100% consensus
        assert len(opps) == 1
        assert opps[0].data["total_timeframes"] == 4

    def test_classify_direction_bullish(self):
        agent = MultiTimeframeConsensusAgent(config=_make_config())
        # RSI oversold + positive MACD + price above EMA = bullish
        direction = agent._classify_direction(
            rsi=25, macd_hist=0.5, ema_trend="above", rsi_overbought=70, rsi_oversold=30
        )
        assert direction == TimeframeDirection.BULLISH

    def test_classify_direction_bearish(self):
        agent = MultiTimeframeConsensusAgent(config=_make_config())
        # RSI overbought + negative MACD + price below EMA = bearish
        direction = agent._classify_direction(
            rsi=75,
            macd_hist=-0.5,
            ema_trend="below",
            rsi_overbought=70,
            rsi_oversold=30,
        )
        assert direction == TimeframeDirection.BEARISH

    def test_classify_direction_neutral(self):
        agent = MultiTimeframeConsensusAgent(config=_make_config())
        # Mixed signals: RSI neutral (50), positive MACD, price below EMA = 1 bullish, 1 bearish = neutral
        direction = agent._classify_direction(
            rsi=50, macd_hist=0.5, ema_trend="below", rsi_overbought=70, rsi_oversold=30
        )
        assert direction == TimeframeDirection.NEUTRAL

    def test_check_consensus_returns_none_for_empty_signals(self):
        agent = MultiTimeframeConsensusAgent(config=_make_config())
        result = agent._check_consensus(
            symbol=Symbol(ticker="AAPL"),
            signals=[],
            min_consensus=0.7,
            min_timeframes_agree=3,
        )
        assert result is None

    async def test_custom_timeframe_weights(self):
        """Higher-weighted timeframes should have more influence."""
        bus = MagicMock()
        bus.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])

        # Lower timeframes bearish, higher timeframes bullish
        # With 1d having weight 3.0, bullish should win
        bus.get_historical = AsyncMock(
            side_effect=[
                _make_bars(100, 150.0, "down"),  # 5m bearish (weight 0.5)
                _make_bars(100, 150.0, "down"),  # 15m bearish (weight 1.0)
                _make_bars(100, 150.0, "down"),  # 1h bearish (weight 1.5)
                _make_bars(100, 150.0, "up"),  # 4h bullish (weight 2.0)
                _make_bars(100, 150.0, "up"),  # 1d bullish (weight 3.0)
            ]
        )

        agent = MultiTimeframeConsensusAgent(config=_make_config())
        opps = await agent.scan(bus)

        # Bullish weight = 2.0 + 3.0 = 5.0
        # Bearish weight = 0.5 + 1.0 + 1.5 = 3.0
        # Total = 8.0, bullish ratio = 62.5% < 70%
        # But bullish_count = 2 < min_timeframes_agree=3
        # So should NOT trigger
        assert len(opps) == 0
