"""Integration tests for Consecutive Loss Circuit Breaker."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from learning.strategy_health import (
    StrategyHealthConfig,
    StrategyHealthEngine,
    StrategyHealthStatus,
)


@pytest.fixture
def mock_health_store():
    store = MagicMock()
    store.get_status = AsyncMock(return_value=None)
    store.upsert_status = AsyncMock()
    store.record_event = AsyncMock()
    return store


@pytest.fixture
def mock_perf_store():
    store = MagicMock()
    return store


class TestConsecutiveLossCircuitBreakerIntegration:
    """Integration tests for the consecutive loss circuit breaker flow."""

    @pytest.mark.asyncio
    async def test_full_flow_triggers_circuit_breaker(
        self, mock_health_store, mock_perf_store
    ):
        """Test that circuit breaker triggers when consecutive losses exceed threshold."""
        mock_perf_store.get_latest = AsyncMock(
            return_value=MagicMock(
                total_trades=50,
                avg_win=Decimal("100"),
                avg_loss=Decimal("50"),
                win_rate=Decimal("0.5"),
                max_drawdown=Decimal("1000"),
                total_pnl=Decimal("500"),
                profit_factor=Decimal("1.5"),
                consecutive_losses=5,  # At threshold
            )
        )

        config = StrategyHealthConfig(
            enabled=True,
            max_consecutive_losses=5,
            consecutive_loss_cooldown_hours=48,
        )

        engine = StrategyHealthEngine(
            health_store=mock_health_store,
            perf_store=mock_perf_store,
            config=config,
        )

        status = await engine.evaluate("test_agent")
        assert status == StrategyHealthStatus.THROTTLED

        # Verify health status was persisted
        mock_health_store.upsert_status.assert_called_once()
        call_kwargs = mock_health_store.upsert_status.call_args[1]
        assert "Circuit breaker" in call_kwargs["trigger_reason"]

    @pytest.mark.asyncio
    async def test_circuit_breaker_overrides_good_performance(
        self, mock_health_store, mock_perf_store
    ):
        """Test that circuit breaker triggers even with good expectancy metrics."""
        mock_perf_store.get_latest = AsyncMock(
            return_value=MagicMock(
                total_trades=50,
                avg_win=Decimal("200"),
                avg_loss=Decimal("10"),
                win_rate=Decimal("0.8"),
                max_drawdown=Decimal("500"),
                total_pnl=Decimal("5000"),
                profit_factor=Decimal("3.0"),
                consecutive_losses=6,  # Above threshold
            )
        )

        config = StrategyHealthConfig(
            enabled=True,
            max_consecutive_losses=5,
        )

        engine = StrategyHealthEngine(
            health_store=mock_health_store,
            perf_store=mock_perf_store,
            config=config,
        )

        status = await engine.evaluate("test_agent")
        assert status == StrategyHealthStatus.THROTTLED

    @pytest.mark.asyncio
    async def test_below_threshold_passes(self, mock_health_store, mock_perf_store):
        """Test that strategy passes when below consecutive loss threshold."""
        mock_perf_store.get_latest = AsyncMock(
            return_value=MagicMock(
                total_trades=50,
                avg_win=Decimal("100"),
                avg_loss=Decimal("50"),
                win_rate=Decimal("0.5"),
                max_drawdown=Decimal("1000"),
                total_pnl=Decimal("500"),
                profit_factor=Decimal("1.5"),
                consecutive_losses=3,  # Below threshold of 5
            )
        )

        config = StrategyHealthConfig(
            enabled=True,
            max_consecutive_losses=5,
        )

        engine = StrategyHealthEngine(
            health_store=mock_health_store,
            perf_store=mock_perf_store,
            config=config,
        )

        status = await engine.evaluate("test_agent")
        assert status in (StrategyHealthStatus.NORMAL, StrategyHealthStatus.WATCHLIST)

    @pytest.mark.asyncio
    async def test_disabled_engine_bypasses_circuit_breaker(
        self, mock_health_store, mock_perf_store
    ):
        """Test that disabled engine doesn't trigger circuit breaker."""
        mock_perf_store.get_latest = AsyncMock(
            return_value=MagicMock(
                total_trades=50,
                consecutive_losses=10,  # Way above threshold
            )
        )

        config = StrategyHealthConfig(enabled=False, max_consecutive_losses=5)

        engine = StrategyHealthEngine(
            health_store=mock_health_store,
            perf_store=mock_perf_store,
            config=config,
        )

        status = await engine.evaluate("test_agent")
        assert status == StrategyHealthStatus.NORMAL
