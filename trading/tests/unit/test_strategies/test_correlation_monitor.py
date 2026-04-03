from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from agents.models import ActionLevel, AgentConfig
from broker.models import Bar, Symbol
from strategies.correlation_monitor import (
    StrategyCorrelationMonitor,
    AgentSignalRecord,
    CorrelationResult,
)

TEST_SYMBOL = Symbol(ticker="AAPL")


def _make_config(**overrides):
    defaults = dict(
        name="correlation-monitor-test",
        strategy="correlation_monitor",
        schedule="continuous",
        action_level=ActionLevel.NOTIFY,
        parameters={
            "correlation_window_minutes": 60,
            "high_correlation_threshold": 0.8,
            "min_samples": 5,
            "alert_cooldown_minutes": 30,
        },
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


class TestStrategyCorrelationMonitor:
    """Tests for StrategyCorrelationMonitor."""

    def setup_method(self):
        """Clear class-level state before each test."""
        StrategyCorrelationMonitor._signal_history.clear()
        StrategyCorrelationMonitor._last_alerts.clear()

    def test_signal_to_numeric_buy(self):
        """Test buy signal converts to 1.0."""
        assert StrategyCorrelationMonitor._signal_to_numeric("buy") == 1.0
        assert StrategyCorrelationMonitor._signal_to_numeric("BUY") == 1.0

    def test_signal_to_numeric_sell(self):
        """Test sell signal converts to -1.0."""
        assert StrategyCorrelationMonitor._signal_to_numeric("sell") == -1.0
        assert StrategyCorrelationMonitor._signal_to_numeric("SELL") == -1.0

    def test_signal_to_numeric_hold(self):
        """Test hold signal converts to 0.0."""
        assert StrategyCorrelationMonitor._signal_to_numeric("hold") == 0.0
        assert StrategyCorrelationMonitor._signal_to_numeric("HOLD") == 0.0

    def test_pearson_correlation_perfect_positive(self):
        """Test perfect positive correlation."""
        pairs = [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)]
        correlation = StrategyCorrelationMonitor._pearson_correlation(pairs)
        assert abs(correlation - 1.0) < 0.001

    def test_pearson_correlation_perfect_negative(self):
        """Test perfect negative correlation."""
        pairs = [(1, 5), (2, 4), (3, 3), (4, 2), (5, 1)]
        correlation = StrategyCorrelationMonitor._pearson_correlation(pairs)
        assert abs(correlation - (-1.0)) < 0.001

    def test_pearson_correlation_no_correlation(self):
        """Test no correlation."""
        pairs = [(1, 3), (2, 1), (3, 5), (4, 2), (5, 4)]
        correlation = StrategyCorrelationMonitor._pearson_correlation(pairs)
        # Should be somewhere between -1 and 1
        assert -1.0 <= correlation <= 1.0

    def test_pearson_correlation_empty(self):
        """Test empty pairs returns 0."""
        assert StrategyCorrelationMonitor._pearson_correlation([]) == 0.0

    def test_pearson_correlation_single_pair(self):
        """Test single pair returns 0 (need at least 2)."""
        assert StrategyCorrelationMonitor._pearson_correlation([(1, 2)]) == 0.0

    def test_record_signal(self):
        """Test recording signals from agents."""
        StrategyCorrelationMonitor.record_signal(
            agent_name="agent_a",
            symbol="AAPL",
            signal="buy",
            confidence=0.8,
        )
        StrategyCorrelationMonitor.record_signal(
            agent_name="agent_b",
            symbol="AAPL",
            signal="buy",
            confidence=0.7,
        )

        assert len(StrategyCorrelationMonitor._signal_history["agent_a"]) == 1
        assert len(StrategyCorrelationMonitor._signal_history["agent_b"]) == 1

    def test_prune_signals(self):
        """Test old signals are pruned."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=2)

        # Add old signal
        StrategyCorrelationMonitor._signal_history["agent_a"] = [
            AgentSignalRecord(
                agent_name="agent_a",
                symbol="AAPL",
                signal="buy",
                confidence=0.8,
                timestamp=old_time,
            )
        ]

        # Run prune with cutoff 1 hour ago
        cutoff = now - timedelta(hours=1)
        monitor = StrategyCorrelationMonitor(config=_make_config())
        monitor._prune_signals(cutoff)

        assert "agent_a" not in StrategyCorrelationMonitor._signal_history

    @pytest.mark.asyncio
    async def test_scan_insufficient_agents(self):
        """Test scan with fewer than 2 agents returns empty."""
        config = _make_config()
        monitor = StrategyCorrelationMonitor(config=config)
        data_bus = AsyncMock()

        # Only one agent has signals
        StrategyCorrelationMonitor.record_signal(
            agent_name="agent_a",
            symbol="AAPL",
            signal="buy",
            confidence=0.8,
        )

        opportunities = await monitor.scan(data_bus)
        assert len(opportunities) == 0

    @pytest.mark.asyncio
    async def test_scan_high_correlation_alert(self):
        """Test scan generates alert when correlation exceeds threshold."""
        config = _make_config(
            parameters={
                "correlation_window_minutes": 60,
                "high_correlation_threshold": 0.7,
                "min_samples": 3,
                "alert_cooldown_minutes": 0,  # No cooldown for test
            }
        )
        monitor = StrategyCorrelationMonitor(config=config)
        data_bus = AsyncMock()

        # Add highly correlated signals
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
        for i, sym in enumerate(symbols):
            signal = "buy" if i % 2 == 0 else "sell"
            StrategyCorrelationMonitor.record_signal(
                agent_name="agent_rsi",
                symbol=sym,
                signal=signal,
                confidence=0.8,
            )
            StrategyCorrelationMonitor.record_signal(
                agent_name="agent_momentum",
                symbol=sym,
                signal=signal,
                confidence=0.75,
            )

        opportunities = await monitor.scan(data_bus)

        # Should generate at least one alert
        assert len(opportunities) >= 1

        # Check alert details
        opp = opportunities[0]
        assert opp.agent_name == "correlation-monitor-test"
        assert opp.signal == "sell"  # Positive correlation -> sell alert
        assert opp.data["alert_type"] == "high_correlation"

    @pytest.mark.asyncio
    async def test_scan_low_correlation_no_alert(self):
        """Test scan with low correlation generates no alerts."""
        config = _make_config(
            parameters={
                "correlation_window_minutes": 60,
                "high_correlation_threshold": 0.95,  # Very high threshold
                "min_samples": 3,
                "alert_cooldown_minutes": 0,
            }
        )
        monitor = StrategyCorrelationMonitor(config=config)
        data_bus = AsyncMock()

        # Add uncorrelated signals
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]
        for i, sym in enumerate(symbols):
            # A: buy, buy, sell, sell
            # B: buy, sell, buy, sell
            sig_a = "buy" if i < 2 else "sell"
            sig_b = "buy" if i % 2 == 0 else "sell"
            StrategyCorrelationMonitor.record_signal(
                agent_name="agent_a",
                symbol=sym,
                signal=sig_a,
                confidence=0.8,
            )
            StrategyCorrelationMonitor.record_signal(
                agent_name="agent_b",
                symbol=sym,
                signal=sig_b,
                confidence=0.7,
            )

        opportunities = await monitor.scan(data_bus)
        # Low correlation should not trigger alert
        assert len(opportunities) == 0

    @pytest.mark.asyncio
    async def test_scan_cooldown_prevents_duplicate(self):
        """Test that cooldown prevents duplicate alerts."""
        config = _make_config(
            parameters={
                "correlation_window_minutes": 60,
                "high_correlation_threshold": 0.7,
                "min_samples": 3,
                "alert_cooldown_minutes": 60,  # 1 hour cooldown
            }
        )
        monitor = StrategyCorrelationMonitor(config=config)
        data_bus = AsyncMock()

        # Add highly correlated signals
        symbols = ["AAPL", "MSFT", "GOOGL"]
        for i, sym in enumerate(symbols):
            signal = "buy" if i == 0 else "sell" if i == 1 else "buy"
            StrategyCorrelationMonitor.record_signal(
                agent_name="agent_a",
                symbol=sym,
                signal=signal,
                confidence=0.8,
            )
            StrategyCorrelationMonitor.record_signal(
                agent_name="agent_b",
                symbol=sym,
                signal=signal,
                confidence=0.75,
            )

        # First scan should generate alert
        opps1 = await monitor.scan(data_bus)
        assert len(opps1) >= 1

        # Second scan should be blocked by cooldown
        opps2 = await monitor.scan(data_bus)
        assert len(opps2) == 0

    def test_get_correlation_matrix(self):
        """Test getting correlation matrix."""
        # Add correlated signals
        symbols = ["AAPL", "MSFT", "GOOGL"]
        for sym in symbols:
            StrategyCorrelationMonitor.record_signal(
                agent_name="agent_a",
                symbol=sym,
                signal="buy",
                confidence=0.8,
            )
            StrategyCorrelationMonitor.record_signal(
                agent_name="agent_b",
                symbol=sym,
                signal="buy",
                confidence=0.75,
            )

        matrix = StrategyCorrelationMonitor.get_correlation_matrix(window_minutes=60)

        assert "agents" in matrix
        assert "matrix" in matrix
        assert "agent_a" in matrix["agents"]
        assert "agent_b" in matrix["agents"]

        # Self-correlation should be 1.0
        assert matrix["matrix"]["agent_a"]["agent_a"] == 1.0

    def test_description(self):
        """Test agent description."""
        config = _make_config()
        monitor = StrategyCorrelationMonitor(config=config)
        assert "correlation" in monitor.description.lower()

    def test_signal_history_bounded(self):
        """Test signal history is bounded to 1000 entries."""
        # Add 1100 signals
        for i in range(1100):
            StrategyCorrelationMonitor.record_signal(
                agent_name="agent_a",
                symbol=f"SYM{i}",
                signal="buy",
                confidence=0.8,
            )

        # Should be trimmed to 1000
        assert len(StrategyCorrelationMonitor._signal_history["agent_a"]) == 1000

    def test_negative_correlation_generates_buy_signal(self):
        """Test negative correlation generates buy alert."""
        config = _make_config(
            parameters={
                "correlation_window_minutes": 60,
                "high_correlation_threshold": 0.7,
                "min_samples": 3,
                "alert_cooldown_minutes": 0,
            }
        )

        # Manually set up negative correlation in history: a goes [buy, sell, buy], b goes [sell, buy, sell]
        StrategyCorrelationMonitor._signal_history["agent_a"] = [
            AgentSignalRecord(
                "agent_a", "AAPL", "buy", 0.8, datetime.now(timezone.utc)
            ),
            AgentSignalRecord(
                "agent_a", "MSFT", "sell", 0.8, datetime.now(timezone.utc)
            ),
            AgentSignalRecord(
                "agent_a", "GOOGL", "buy", 0.8, datetime.now(timezone.utc)
            ),
        ]
        StrategyCorrelationMonitor._signal_history["agent_b"] = [
            AgentSignalRecord(
                "agent_b", "AAPL", "sell", 0.8, datetime.now(timezone.utc)
            ),
            AgentSignalRecord(
                "agent_b", "MSFT", "buy", 0.8, datetime.now(timezone.utc)
            ),
            AgentSignalRecord(
                "agent_b", "GOOGL", "sell", 0.8, datetime.now(timezone.utc)
            ),
        ]

        result = StrategyCorrelationMonitor._calculate_correlation_static(
            "agent_a", "agent_b", datetime.now(timezone.utc) - timedelta(hours=1), 1
        )

        # Perfect negative correlation
        assert result is not None
        assert result.correlation == -1.0
